"""LiteLLM gateway: key pool, automatic failover, built-in response cache."""
import logging
import os
from dataclasses import dataclass

import litellm
from litellm import Cache

log = logging.getLogger("llm")
litellm.suppress_debug_info = True


class AllProvidersUnavailable(Exception):
    """Every key in the pool failed for this request."""


@dataclass
class LLMResult:
    reply: str
    cached: bool
    key_id: str | None
    fallback_attempts: int
    input_tokens: int
    output_tokens: int


def init_cache() -> None:
    """Enable LiteLLM's built-in in-memory cache."""
    litellm.cache = Cache(type="local")


def cache_enabled() -> bool:
    return litellm.cache is not None


def parse_simulation(header: str | None) -> dict[str, int]:
    """'key_1=429,key_2=500' or '*=429' -> {'key_1': 429, ...}. Bad pairs are ignored."""
    sim: dict[str, int] = {}
    if not header:
        return sim
    for pair in header.split(","):
        name, _, status = pair.strip().partition("=")
        if name and status.strip() in {"429", "500", "502", "503"}:
            sim[name.strip()] = int(status)
    return sim


def complete(messages: list[dict], keys: list[str], model: str,
             simulate: dict[str, int] | None = None, timeout: float = 30) -> LLMResult:
    simulate = simulate or {}
    # A simulated failure must produce a real, live answer from the next key,
    # so the cache is bypassed for that request only.
    use_cache = not simulate
    attempts = 0

    for index, key in enumerate(keys, start=1):
        key_id = f"key_{index}"
        status = simulate.get(key_id, simulate.get("*"))
        if status:
            log.warning("simulated %s on %s", status, key_id)
            attempts += 1
            continue
        try:
            kwargs = dict(model=model, messages=messages, api_key=key,
                          caching=use_cache, num_retries=0, timeout=timeout)
            mock = os.getenv("LLM_MOCK_RESPONSE")  # offline demo / tests only
            if mock:
                kwargs["mock_response"] = mock
            resp = litellm.completion(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise ValueError("empty completion")
        except Exception as exc:  # 429, quota, 5xx, auth, timeout... all fail over
            log.warning("%s failed (%s): %s", key_id, type(exc).__name__, exc)
            attempts += 1
            continue

        cached = bool(getattr(resp, "_hidden_params", {}).get("cache_hit"))
        usage = getattr(resp, "usage", None)
        return LLMResult(
            reply=text,
            cached=cached,
            key_id=None if cached else key_id,
            fallback_attempts=0 if cached else attempts,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    raise AllProvidersUnavailable()
