# Relay Chat: LLM chatbot with key failover and response caching

A full-stack chatbot built with React, FastAPI, LiteLLM and SQLite. It keeps multi-turn history per session, fails over across a pool of API keys, caches responses, and shows per-request metadata next to every reply.

## 1. Live URLs

- Frontend: `https://<your-frontend>.vercel.app` (replace after deploying)
- Backend: `https://<your-backend>.onrender.com` (replace after deploying)
- Health check: `<backend>/health`
- Demo video: `<link>`

## 2. Run locally

### With Docker

```bash
cp .env.example .env      # then put 2+ real keys in LLM_API_KEYS
make up                   # frontend :3000, backend :8000
make down                 # stop (history persists in the named volume)
```

### Without Docker

```bash
# backend
cd backend
pip install -r requirements-dev.txt
export LLM_API_KEYS=key-one,key-two ENABLE_FAILURE_SIMULATION=true DATABASE_URL=sqlite:///./app.db
uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

Run the backend tests with `make test`. They need no real API keys.

## 3. Design decisions

**Key fallback.** `LLM_API_KEYS` is parsed into `key_1`, `key_2`, and so on. For each request, `llm.complete` tries the keys in order through `litellm.completion`. Any exception (429, quota, 5xx, timeout, auth) moves on to the next key and increments `fallback_attempts`. If every key fails, the API returns `503 {"detail": "all providers unavailable"}` and nothing is written to history. LiteLLM's own retries are disabled (`num_retries=0`) so failover is immediate and the attempt count is accurate. Key values are never returned or logged, only ids.

**Caching.** LiteLLM's built-in in-memory cache is enabled at startup. Its cache key covers the model and the full message list (system prompt, history and new message), so the same first message in a new session is a hit, and a different message never is. A hit is detected from LiteLLM's `cache_hit` flag, reported as `LLM_CACHE` with `key_id: null` and the token usage stored with the cached response. Latency is measured by the server for each request, so hits are visibly faster. The cache is in memory, so it resets when the container restarts.

**SQLite session storage.** The `messages` table follows the required schema, with a `sessions` table that stores the optional per-session system prompt. History is read from SQLite on each request, so the client only sends the new message. A turn (user and assistant rows) is written in one transaction after the model succeeds, so failed requests (422 or 503) never appear in history. The file lives at `DATABASE_URL`, on the `/data` Docker volume.

**Per-request tokens.** `input_tokens` and `output_tokens` come from the provider's usage for that single call. The input count includes system prompt, history and the new message, and nothing is accumulated.

**Failure simulation.** `X-Simulate-Failure` is honored only when `ENABLE_FAILURE_SIMULATION=true`. Listed keys are skipped as if they had returned the given status, and the next key makes a real call. The cache is bypassed for simulated requests so the demo always shows a live answer from the fallback key.

## 4. Verification

```bash
BASE=http://localhost:8000
curl $BASE/health

# Live call, then the same message in a NEW session returns LLM_CACHE with key_id null
curl -s $BASE/chat -H 'content-type: application/json' -d '{"session_id":"a1","message":"What is the capital of France?"}'
curl -s $BASE/chat -H 'content-type: application/json' -d '{"session_id":"b2","message":"What is the capital of France?"}'

# Failover: answered by key_2 with fallback_attempts 1
curl -s $BASE/chat -H 'content-type: application/json' -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"c3","message":"Name a prime number."}'

# All keys fail: 503, and the session is not created
curl -si $BASE/chat -H 'content-type: application/json' -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"d4","message":"Name a prime number."}'
curl -i $BASE/sessions/d4/messages    # 404

# History, oldest first, without the system prompt
curl -s $BASE/sessions/a1/messages
```

In the UI, each assistant reply shows its source, model, latency and input and output tokens. Send the same question in two chats to see `LLM_CACHE`, and watch input tokens grow within one chat as history is included.

## 5. Setup Used

- Editor: VS Code (replace with yours)
- AI tools: Claude (replace or add anything else you used)

## 6. Bonus features

- Per-session system prompt field in the UI, stored per session in SQLite.
- Route field in each reply's metadata (`key_N` or `cache`, plus failover count) to make failover visible.
- Starter questions, new-chat button and readable inline errors for 422 and 503.
- 11 backend tests covering validation, caching, failover (simulated and real), the 503 path and session isolation.
- Non-root backend container and a SQLite WAL journal for safer concurrent reads.
