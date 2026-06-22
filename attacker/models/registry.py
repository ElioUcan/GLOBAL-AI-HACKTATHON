"""NVIDIA NIM model registry and evidence matrix for the Attacker Agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AttackerRole(str, Enum):
    BASE = "base"
    VALIDATION = "validation"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class NimModelSpec:
    """One candidate attacker model with its expected evidence profile."""

    slug: str
    litellm_id: str
    role: AttackerRole
    rejection_rate: str
    sis_expectation: str
    cost_tier: str
    ideal_pipeline_role: str
    temperature: float = 0.9
    max_tokens: int = 512

    @property
    def short_name(self) -> str:
        return self.slug.split("/")[-1]


def _litellm(slug: str) -> str:
    return f"openrouter/{slug}"


# Attacker models — served via OpenRouter (OPENROUTER_API_KEY).
# Two-model lineup: a high-capacity validation attacker and a base attacker.
# No dedicated fallback model; the fallback reuses the base attacker.
ATTACKER_MODEL_REGISTRY: dict[str, NimModelSpec] = {
    "validation": NimModelSpec(
        slug="nousresearch/hermes-3-llama-3.1-405b",
        litellm_id=_litellm("nousresearch/hermes-3-llama-3.1-405b"),
        role=AttackerRole.VALIDATION,
        rejection_rate="very_low",
        sis_expectation="high",
        cost_tier="high",
        ideal_pipeline_role=(
            "Atacante de validación avanzada / generador de técnicas complejas"
        ),
    ),
    "base": NimModelSpec(
        slug="meta-llama/llama-3.1-70b-instruct",
        litellm_id=_litellm("meta-llama/llama-3.1-70b-instruct"),
        role=AttackerRole.BASE,
        rejection_rate="low_medium",
        sis_expectation="medium_high",
        cost_tier="moderate",
        ideal_pipeline_role="Atacante base (default) para la mayoría de técnicas",
    ),
}

DEFAULT_BASE_MODEL = ATTACKER_MODEL_REGISTRY["base"]
DEFAULT_VALIDATION_MODEL = ATTACKER_MODEL_REGISTRY["validation"]
# No dedicated fallback model in this lineup; reuse the base attacker.
DEFAULT_FALLBACK_MODEL = ATTACKER_MODEL_REGISTRY["base"]

CALIBRATION_CANDIDATES: list[NimModelSpec] = list(ATTACKER_MODEL_REGISTRY.values())

# Patrones que indican self-refusal del modelo atacante (no del target)
SELF_REFUSAL_PATTERNS: tuple[str, ...] = (
    "i can't help",
    "i cannot help",
    "i'm unable to",
    "i am unable to",
    "cannot assist",
    "can't assist",
    "against my guidelines",
    "violates my",
    "not able to generate",
    "no puedo ayudar",
    "no puedo generar",
    "no estoy autorizado",
    "lo siento, no puedo",
    "como modelo de lenguaje",
    "como asistente de ia",
)


def resolve_model(litellm_id: str) -> NimModelSpec | None:
    """Look up a registry entry by LiteLLM model id."""
    for spec in ATTACKER_MODEL_REGISTRY.values():
        if spec.litellm_id == litellm_id:
            return spec
    return None


def models_by_role(role: AttackerRole) -> list[NimModelSpec]:
    return [m for m in ATTACKER_MODEL_REGISTRY.values() if m.role == role]
