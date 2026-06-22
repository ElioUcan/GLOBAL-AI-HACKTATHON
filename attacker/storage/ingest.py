"""Corpus ingestion: HarmBench ES + slang corpus → PostgreSQL.

Loads the Spanish HarmBench control prompts into ``harmbench_behaviors`` and
pairs each curated slang term with HarmBench behaviors, repopulating ``jerga``
(+ ``jerga_metadata``) for the benchmark.

Scope (current benchmark): only two HarmBench semantic categories are used,
with HarmBench naming kept verbatim so ``jerga.harm_category`` equals
``harmbench_behaviors.semantic_category`` (identity join):

  - chemical_biological   (Chemical & Biological Weapons / Drugs)
  - harassment_bullying    (Harassment & Bullying)

Idempotent for HarmBench (skips if rows exist); ``jerga`` and
``jerga_metadata`` are truncated and rebuilt on every apply.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from attacker.storage.db import get_connection

# ── Paths (repo-root relative) ─────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = _ROOT / "USELESS/leandro/datasets/originales/dataset_combinado.json"
DEFAULT_HARMBENCH = _ROOT / "harmbench_behaviors_text_no_copyright_es.csv"

INGEST_VERSION = "0.3.0-2cat"

# Only these HarmBench categories are in scope. harm_category == semantic_category.
TARGET_CATEGORIES: tuple[str, ...] = ("chemical_biological", "harassment_bullying")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ── Loaders ─────────────────────────────────────────────────────────────────
def load_corpus(path: Path, min_confianza: int) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entradas = raw if isinstance(raw, list) else raw.get("entradas", [])
    out = []
    for e in entradas:
        conf = e.get("confianza")
        if conf is None or conf < min_confianza:
            continue
        termino = (e.get("termino") or "").strip()
        significado = (e.get("significado") or "").strip()
        if not termino or not significado:
            continue
        out.append(e)
    out.sort(key=lambda x: (x.get("termino", "").lower(), x.get("id_fusion", "")))
    return out


def load_harmbench(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r["BehaviorID"])
    return rows


# ── Schema ────────────────────────────────────────────────────────────────
def ensure_tables(conn) -> None:
    """Create harmbench_behaviors and jerga_metadata if they don't exist.

    Mirrors docker/postgres/init/01-schema.sql so running databases created
    before that schema update get the missing tables without a volume reset.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS harmbench_behaviors (
        behavior_id         TEXT PRIMARY KEY,
        behavior            TEXT NOT NULL,
        functional_category TEXT,
        semantic_category   TEXT NOT NULL,
        tags                TEXT,
        context_string      TEXT,
        source_file         TEXT NOT NULL DEFAULT 'harmbench_behaviors_text_no_copyright_es.csv',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_harmbench_semantic
        ON harmbench_behaviors(semantic_category);
    CREATE INDEX IF NOT EXISTS idx_harmbench_functional
        ON harmbench_behaviors(functional_category);

    CREATE TABLE IF NOT EXISTS jerga_metadata (
        jerga_id           INTEGER PRIMARY KEY REFERENCES jerga(id) ON DELETE CASCADE,
        behavior_id        TEXT REFERENCES harmbench_behaviors(behavior_id),
        semantic_category  TEXT NOT NULL,
        corpus_id_fusion   TEXT,
        confianza          SMALLINT,
        procedencia        TEXT,
        tags               JSONB NOT NULL DEFAULT '[]'::jsonb,
        fuentes            JSONB NOT NULL DEFAULT '[]'::jsonb,
        pos                TEXT,
        nivel_formalidad   TEXT,
        ingest_source      TEXT NOT NULL,
        ingest_version     TEXT NOT NULL,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_jerga_metadata_behavior
        ON jerga_metadata(behavior_id);
    CREATE INDEX IF NOT EXISTS idx_jerga_metadata_semantic
        ON jerga_metadata(semantic_category);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()


def ingest_harmbench(conn, behaviors: list[dict], source_file: str) -> int:
    """Insert HarmBench behaviors. Idempotent: skip entirely if table populated."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM harmbench_behaviors;")
        if cur.fetchone()[0] > 0:
            return 0
        inserted = 0
        for b in behaviors:
            cur.execute(
                """
                INSERT INTO harmbench_behaviors (
                    behavior_id, behavior, functional_category,
                    semantic_category, tags, context_string, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (behavior_id) DO NOTHING;
                """,
                (
                    b["BehaviorID"],
                    b["Behavior"],
                    b.get("FunctionalCategory") or "standard",
                    b["SemanticCategory"],
                    b.get("Tags") or "",
                    b.get("ContextString") or "",
                    source_file,
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


# ── Pairing ──────────────────────────────────────────────────────────────
def bucket_behaviors(behaviors: list[dict]) -> dict[str, list[dict]]:
    """Group in-scope HarmBench behaviors by semantic_category (identity map)."""
    pools: dict[str, list[dict]] = {c: [] for c in TARGET_CATEGORIES}
    for b in behaviors:
        sem = b["SemanticCategory"]
        if sem in pools:
            pools[sem].append(b)
    for cat in TARGET_CATEGORIES:
        pools[cat].sort(key=lambda r: r["BehaviorID"])
        if not pools[cat]:
            raise SystemExit(
                f"No HarmBench behaviors found for semantic_category={cat!r}."
            )
    return pools


def assign_behaviors(terms: list[dict], pools: dict[str, list[dict]]) -> list[dict]:
    """Pair each term with one behavior per target category (balanced round-robin)."""
    counters = {c: 0 for c in TARGET_CATEGORIES}
    pairs: list[dict] = []
    for term in terms:
        for cat in TARGET_CATEGORIES:
            pool = pools[cat]
            beh = pool[counters[cat] % len(pool)]
            counters[cat] += 1
            pairs.append({"term": term, "behavior": beh})
    return pairs


def build_rows(pairs: list[dict], *, corpus_path: Path) -> list[dict]:
    rows = []
    src = Path(corpus_path).name
    for pair in pairs:
        t = pair["term"]
        b = pair["behavior"]
        semantic = b["SemanticCategory"]
        rows.append(
            {
                "term": t["termino"],
                "meaning": t["significado"],
                "base_intent": b["Behavior"],
                "harm_category": semantic,  # identity: harm_category == semantic_category
                "region": t.get("region") or "General México",
                "metadata": {
                    "behavior_id": b["BehaviorID"],
                    "semantic_category": semantic,
                    "corpus_id_fusion": t.get("id_fusion"),
                    "confianza": t.get("confianza"),
                    "procedencia": t.get("procedencia"),
                    "tags": t.get("tags") or [],
                    "fuentes": t.get("fuentes") or [],
                    "pos": t.get("pos"),
                    "nivel_formalidad": t.get("nivel_formalidad"),
                    "ingest_source": src,
                    "ingest_version": INGEST_VERSION,
                },
            }
        )
    return rows


def apply_jerga(conn, rows: list[dict]) -> None:
    """Truncate jerga (+ metadata) and insert the paired rows."""
    with conn.cursor() as cur:
        cur.execute("TRUNCATE jerga_metadata")
        cur.execute("TRUNCATE jerga RESTART IDENTITY CASCADE")
        for row in rows:
            cur.execute(
                """
                INSERT INTO jerga (term, meaning, base_intent, harm_category, region)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    row["term"],
                    row["meaning"],
                    row["base_intent"],
                    row["harm_category"],
                    row["region"],
                ),
            )
            jerga_id = cur.fetchone()[0]
            m = row["metadata"]
            cur.execute(
                """
                INSERT INTO jerga_metadata (
                    jerga_id, behavior_id, semantic_category,
                    corpus_id_fusion, confianza, procedencia,
                    tags, fuentes, pos, nivel_formalidad,
                    ingest_source, ingest_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    jerga_id,
                    m["behavior_id"],
                    m["semantic_category"],
                    m["corpus_id_fusion"],
                    m["confianza"],
                    m["procedencia"],
                    json.dumps(m["tags"], ensure_ascii=False),
                    json.dumps(m["fuentes"], ensure_ascii=False),
                    m["pos"],
                    m["nivel_formalidad"],
                    m["ingest_source"],
                    m["ingest_version"],
                ),
            )
    conn.commit()


# ── Orchestration ───────────────────────────────────────────────────────────
def run_ingest(
    *,
    corpus: Path = DEFAULT_CORPUS,
    harmbench: Path = DEFAULT_HARMBENCH,
    min_confianza: int = 2,
    dry_run: bool = False,
) -> int:
    corpus = Path(corpus)
    harmbench = Path(harmbench)
    if not corpus.is_file():
        print(f"Corpus not found: {corpus}")
        return 1
    if not harmbench.is_file():
        print(f"HarmBench CSV not found: {harmbench}")
        return 1

    terms = load_corpus(corpus, min_confianza)
    behaviors = load_harmbench(harmbench)
    pools = bucket_behaviors(behaviors)
    pairs = assign_behaviors(terms, pools)
    rows = build_rows(pairs, corpus_path=corpus)

    harm = Counter(r["harm_category"] for r in rows)
    print(f"=== Ingest plan ({_now_iso()}) ===")
    print(f"  Terms (confianza>={min_confianza}): {len(terms)}")
    print(f"  HarmBench pools: " + ", ".join(f"{c}={len(pools[c])}" for c in TARGET_CATEGORIES))
    print(f"  jerga rows to write: {len(rows)}  by harm_category: {dict(harm)}")

    if dry_run:
        print("\n[dry-run] Nothing written.")
        return 0

    conn = get_connection()
    try:
        ensure_tables(conn)
        n_hb = ingest_harmbench(conn, behaviors, harmbench.name)
        print(f"  harmbench_behaviors: +{n_hb} new (0 = already populated)")
        apply_jerga(conn, rows)
        verify(conn)
    finally:
        conn.close()
    print("\n✓ Ingest applied.")
    return 0


def verify(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM jerga;")
        n_jerga = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM jerga_metadata;")
        n_meta = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM harmbench_behaviors;")
        n_hb = cur.fetchone()[0]
        cur.execute(
            "SELECT harm_category, COUNT(*) FROM jerga GROUP BY harm_category ORDER BY harm_category;"
        )
        harm = dict(cur.fetchall())
    print("\n=== DB verification ===")
    print(f"  jerga={n_jerga}  jerga_metadata={n_meta}  harmbench_behaviors={n_hb}")
    print(f"  jerga by harm_category: {harm}")
