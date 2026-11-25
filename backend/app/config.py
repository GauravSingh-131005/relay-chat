"""Environment-driven configuration. Read lazily so tests can change env vars."""
import os

DEFAULT_SYSTEM_PROMPT = "You are a helpful, concise assistant."


def api_keys() -> list[str]:
    raw = os.getenv("LLM_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def model() -> str:
    return os.getenv("LLM_MODEL", "gemini/gemini-3.5-flash-lite")


def allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return [o.strip() for o in raw.split(",") if o.strip()]


def simulation_enabled() -> bool:
    return os.getenv("ENABLE_FAILURE_SIMULATION", "false").strip().lower() == "true"


def default_system_prompt() -> str:
    return os.getenv("DEFAULT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)


def request_timeout() -> float:
    return float(os.getenv("LLM_TIMEOUT", "30"))
