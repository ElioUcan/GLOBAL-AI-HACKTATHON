# Yucatan Slang Jailbreak Benchmark

## Technologies

![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=for-the-badge&logo=grafana&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-EA4B71?style=for-the-badge&logo=n8n&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2CA5E0?style=for-the-badge&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![NVIDIA NIM](https://img.shields.io/badge/NVIDIA%20NIM-76B900?style=for-the-badge&logo=nvidia&logoColor=white)

## Features

- **Attacker Agent** — generates adversarial prompts by embedding Yucatan/Mexican slang into harmful-intent requests using seven distinct attack techniques (translation transfer, semantic obfuscation, roleplay wrap, and more)
- **Target Agent** — swappable LLM under test via a **dual-API strategy**: open-weight models through NVIDIA NIM plus highly-aligned frontier models (Claude 3.5 Sonnet, GPT-4o) through OpenRouter, selected purely by model slug with no code changes
- **Judge Agent** — evaluates each response with a deterministic LLM call, returning a structured verdict (`jailbreak_success`, `confidence`, `severity`, `reasoning`); it is the **sole arbiter** of whether an attempt counts as a jailbreak
- **PAIR Loop** — iterative multi-turn attack: the attacker refines its prompt based on judge feedback for up to five iterations, stopping early on a confirmed jailbreak
- **Regex Pre-filter** — a cheap heuristic that short-circuits only clear refusals (to save Judge tokens); it can never flag a success on its own, so the Judge always confirms potential harm
- **PostgreSQL Storage** — every attack attempt, response, and verdict is persisted in a structured schema queryable across models, techniques, and harm categories
- **Grafana Dashboards** — live visualization of jailbreak success rates broken down by model, attack technique, and harm category

## Uses

This benchmark is used by AI safety researchers and hackathon teams to measure how well LLM safety filters resist adversarial prompts written in regional Mexican and Yucatecan slang. The goal is to surface alignment blind spots caused by underrepresented languages and dialects, producing quantifiable results that can inform model fine-tuning and safety evaluation pipelines.

## Process

The system is orchestrated entirely through n8n workflows: the Attacker Agent reads slang terms from PostgreSQL, calls an NVIDIA NIM LLM via API key to generate an adversarial prompt, forwards it to the Target LLM, then passes both prompt and response to the Judge Agent for scoring. All structured results are written back to PostgreSQL. Grafana connects directly to PostgreSQL to render live dashboards — no intermediate data pipeline needed. The entire stack runs locally in Docker Compose, making it reproducible across team members without any cloud infrastructure dependency.

<img width="2263" height="951" alt="image" src="https://github.com/user-attachments/assets/3f969157-a90f-4ab3-8064-d3304c8e0439" />

## Quick start (first-time setup)

Run these steps in order. Steps 1–2 bring up the infrastructure, steps 3–4 set up
the Python CLI, step 5 loads the data, and step 6 runs the benchmark.

### Prerequisites

- **Docker** + **Docker Compose**
- **Python 3.10+** (3.14 works)
- An **NVIDIA NIM API key** — free at <https://build.nvidia.com>. Powers the attacker, judge,
  SIS evaluator, and all open-weight (`nvidia_nim/*`) targets.
- *(Optional)* An **OpenRouter API key** — <https://openrouter.ai/keys>. Only needed to test the
  "hard" targets (`openrouter/anthropic/claude-3.5-sonnet`, `openrouter/openai/gpt-4o`).

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and set NVIDIA_API_KEY (required).
# Optionally set OPENROUTER_API_KEY to run openrouter/* targets.
```

### 2. Start the stack (PostgreSQL + n8n + Grafana)

```bash
docker compose up -d --build
```

| Service | URL | Credentials |
|---|---|---|
| n8n (workflow editor) | http://localhost:5678 | — |
| Grafana (dashboards) | http://localhost:3000 | admin / admin |
| PostgreSQL | localhost:5432 | admin / slang_bench |

### 3. Create a Python environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r attacker/requirements.txt -r scripts/requirements.txt
```

### 4. Load the slang corpus

The Docker init script seeds only **10 demo rows**. Load the full **1,575-row** corpus
(525 slang terms × 3 harm categories, each paired with a HarmBench `base_intent`) from
`datasets/`:

```bash
.venv/bin/python scripts/ingest_slang_bench.py --apply
```

Verify it loaded (should print `1575`):

```bash
docker exec slang_postgres psql -U admin -d slang_bench -t -c "SELECT count(*) FROM jerga;"
```

### 5. Run the benchmark

```bash
# 230 attacks, rotating through all 7 techniques, against the gemma-2-2b target.
# NIM_ITER_DELAY=2 paces calls to avoid rate limits.
NIM_ITER_DELAY=2 .venv/bin/python -m attacker.main run \
  --limit 230 \
  --target nvidia_nim/google/gemma-2-2b-it

# Quick smoke test (5 attacks)
.venv/bin/python -m attacker.main run --limit 5
```

### 6. View results

- **Grafana dashboards:** http://localhost:3000 → *Jailbreak Metrics*
- **Or query the DB directly:**

```bash
docker exec slang_postgres psql -U admin -d slang_bench -c "SELECT * FROM v_asr_general;"
```

---

## CLI reference

The pipeline (`Fetch Jerga → Attacker → Target → Regex pre-filter → Judge → Storage`) is run
as a module:

```bash
python -m attacker.main <subcommand>
```

| Subcommand | Description |
|---|---|
| `run` | Run the full benchmark pipeline |
| `models` | Print the attacker model registry |

**`run` flags:**

| Flag | Description | Default |
|---|---|---|
| `--target` | Target model slug (NVIDIA NIM or OpenRouter) | `nvidia_nim/meta/llama-3.1-8b-instruct` |
| `--technique` | Fixed attack technique; omit to rotate through all seven | rotate |
| `--limit` | Max number of attack iterations (capped by corpus size) | `100` |
| `--attacker-model` | Force a specific attacker model slug | registry default |

**Supported targets (dual-API):**

| Slug | Provider | Key required |
|---|---|---|
| `nvidia_nim/meta/llama-3.1-8b-instruct` | NVIDIA NIM | `NVIDIA_API_KEY` |
| `nvidia_nim/google/gemma-2-9b-it` | NVIDIA NIM | `NVIDIA_API_KEY` |
| `nvidia_nim/google/gemma-2-2b-it` | NVIDIA NIM | `NVIDIA_API_KEY` |
| `nvidia_nim/mistralai/mistral-7b-instruct-v0.3` | NVIDIA NIM | `NVIDIA_API_KEY` |
| `nvidia_nim/qwen/qwen2-7b-instruct` | NVIDIA NIM | `NVIDIA_API_KEY` |
| `openrouter/anthropic/claude-3.5-sonnet` | OpenRouter | `OPENROUTER_API_KEY` |
| `openrouter/openai/gpt-4o` | OpenRouter | `OPENROUTER_API_KEY` |

**Valid techniques:** `translation_transfer`, `semantic_obfuscation`, `crescendo`,
`codeswitching`, `roleplay_wrap`, `manyshot_slang`, `pair_refine`.

---

## Managing the stack

```bash
docker compose down       # stop services (data is kept in Docker volumes)
docker compose down -v    # stop AND wipe all data (Postgres volume reset)
```

> ⚠️ After `docker compose down -v`, the `jerga` table drops back to the 10-row seed.
> Re-run the corpus load (step 4) to restore the full 1,575 rows before benchmarking.
