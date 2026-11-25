"""FastAPI app exposing /health, /chat and /sessions/{id}/messages."""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import config, db, llm

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    llm.init_cache()
    log.info("ready: %d key(s), model=%s", len(config.api_keys()), config.model())
    yield


app = FastAPI(title="LLM Chatbot Gateway", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: str | None = Field(default=None, max_length=4000)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")}
              for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/health")
def health():
    ok = db.ping()
    keys = len(config.api_keys())
    if not ok or keys == 0:
        raise HTTPException(status_code=503, detail="not ready")
    return {"status": "ok", "keys_configured": keys, "cache_enabled": llm.cache_enabled()}


@app.post("/chat")
def chat(req: ChatRequest, x_simulate_failure: str | None = Header(default=None)):
    started = time.perf_counter()

    system_prompt = (req.system_prompt or "").strip() or None
    system = system_prompt or db.get_system_prompt(req.session_id) or config.default_system_prompt()
    history = db.get_history(req.session_id)

    messages = [{"role": "system", "content": system}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": req.message})

    simulate = llm.parse_simulation(x_simulate_failure) if config.simulation_enabled() else {}

    try:
        result = llm.complete(messages, config.api_keys(), config.model(),
                              simulate=simulate, timeout=config.request_timeout())
    except llm.AllProvidersUnavailable:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    metadata = {
        "resolution_source": "LLM_CACHE" if result.cached else "LIVE_INFERENCE",
        "model": config.model(),
        "latency_ms": max(1, int((time.perf_counter() - started) * 1000)),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "key_id": result.key_id,
        "fallback_attempts": result.fallback_attempts,
    }
    db.add_exchange(req.session_id, req.message, result.reply, metadata, system_prompt)
    return {"session_id": req.session_id, "reply": result.reply, "metadata": metadata}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    messages = db.get_history(session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": messages}
