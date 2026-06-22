"""LiteLLM client for NVIDIA NIM with retry/backoff on transient errors."""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Any

# Default retry policy (override via env).
_MAX_RETRIES = int(os.getenv("NIM_MAX_RETRIES", "5"))
_BACKOFF_BASE = float(os.getenv("NIM_BACKOFF_BASE", "2.0"))  # seconds
_BACKOFF_CAP = float(os.getenv("NIM_BACKOFF_CAP", "60.0"))   # seconds


def _retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Transient LiteLLM errors worth retrying (rate limit, 5xx, network)."""
    import litellm

    names = (
        "RateLimitError",
        "Timeout",
        "APIConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
    )
    exc = tuple(
        getattr(litellm, name) for name in names if hasattr(litellm, name)
    )
    return exc or (Exception,)


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Honor a server-provided Retry-After header if available."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sleep_for(exc: BaseException, attempt: int) -> float:
    """Compute the delay before the next attempt (1-indexed attempt number)."""
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return retry_after
    # Exponential backoff with full jitter, capped.
    backoff = min(_BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_CAP)
    return backoff + random.uniform(0, 1)


def _provider_kwargs(model: str) -> dict[str, str]:
    """Provider-specific credentials based on the LiteLLM model prefix.

    - ``openrouter/...`` → OpenRouter (OPENROUTER_API_KEY); LiteLLM sets the base.
    - anything else      → NVIDIA NIM (NVIDIA_API_KEY + NVIDIA_API_BASE).
    """
    if model.startswith("openrouter/"):
        key = os.getenv("OPENROUTER_API_KEY")
        return {"api_key": key} if key else {}
    return {
        "api_key": os.getenv("NVIDIA_API_KEY"),
        "api_base": os.getenv("NVIDIA_API_BASE", "https://integrate.api.nvidia.com/v1"),
    }


def completion(model: str, messages: list[dict[str, str]], **kwargs) -> Any:
    """Thin LiteLLM wrapper that injects provider credentials and retries.

    Routes to OpenRouter or NVIDIA NIM based on the model prefix. Transient
    failures (HTTP 429 / 5xx / connection / timeout) are retried up to
    ``NIM_MAX_RETRIES`` times with exponential backoff + jitter, honoring a
    ``Retry-After`` header when the server sends one.
    """
    import litellm

    # Silence litellm's noisy stdout banners (e.g. "Provider List: ...") emitted
    # when a model is missing from its pricing map — cosmetic, not an error.
    litellm.suppress_debug_info = True

    retryable = _retryable_exceptions()
    provider_kwargs = _provider_kwargs(model)

    attempt = 0
    while True:
        try:
            return litellm.completion(
                model=model,
                messages=messages,
                **provider_kwargs,
                **kwargs,
            )
        except retryable as exc:
            attempt += 1
            if attempt > _MAX_RETRIES:
                raise
            delay = _sleep_for(exc, attempt)
            print(
                f"[nim_client] {type(exc).__name__} on {model} — retry "
                f"{attempt}/{_MAX_RETRIES} in {delay:.1f}s",
                file=sys.stderr,
            )
            time.sleep(delay)


def extract_token_usage(response: Any) -> tuple[int, int]:
    """Return (prompt_tokens, completion_tokens) from a LiteLLM response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    return int(prompt), int(completion)
