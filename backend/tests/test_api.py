import litellm
from conftest import uid


def chat(client, session, message, headers=None, **extra):
    body = {"session_id": session, "message": message, **extra}
    return client.post("/chat", json=body, headers=headers or {})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "keys_configured": 2, "cache_enabled": True}


def test_validation_errors(client):
    assert client.post("/chat", json={"session_id": "s", "message": "   "}).status_code == 422
    assert client.post("/chat", json={"message": "hi"}).status_code == 422
    assert client.post("/chat", json={"session_id": "s", "message": "x" * 4001}).status_code == 422
    r = client.post("/chat", content="{oops", headers={"content-type": "application/json"})
    assert r.status_code == 422 and "detail" in r.json()


def test_live_response_shape(client):
    r = chat(client, f"s-{uid()}", f"hello {uid()}")
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["resolution_source"] == "LIVE_INFERENCE"
    assert meta["key_id"] == "key_1" and meta["fallback_attempts"] == 0
    assert isinstance(meta["latency_ms"], int)
    assert meta["input_tokens"] > 0 and meta["output_tokens"] > 0


def test_cache_hit_in_new_session(client):
    msg = f"capital of France? {uid()}"
    first = chat(client, f"s-{uid()}", msg).json()
    second = chat(client, f"s-{uid()}", msg).json()
    assert second["metadata"]["resolution_source"] == "LLM_CACHE"
    assert second["reply"] == first["reply"]
    assert second["metadata"]["key_id"] is None
    assert second["metadata"]["fallback_attempts"] == 0
    assert second["metadata"]["input_tokens"] == first["metadata"]["input_tokens"]


def test_different_message_is_not_cached(client):
    chat(client, f"s-{uid()}", f"alpha {uid()}")
    other = chat(client, f"s-{uid()}", f"beta {uid()}").json()
    assert other["metadata"]["resolution_source"] == "LIVE_INFERENCE"


def test_history_and_session_isolation(client):
    a, b = f"s-{uid()}", f"s-{uid()}"
    chat(client, a, f"one {uid()}")
    chat(client, a, f"two {uid()}")
    chat(client, b, f"other {uid()}")
    msgs = client.get(f"/sessions/{a}/messages").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert "metadata" in msgs[1] and "metadata" not in msgs[0]
    assert len(client.get(f"/sessions/{b}/messages").json()["messages"]) == 2
    assert client.get("/sessions/nope/messages").status_code == 404


def test_simulated_failover(client):
    r = chat(client, f"s-{uid()}", f"sim {uid()}", {"X-Simulate-Failure": "key_1=429"})
    assert r.status_code == 200
    meta = r.json()["metadata"]
    assert meta["key_id"] == "key_2" and meta["fallback_attempts"] == 1
    r = chat(client, f"s-{uid()}", f"sim {uid()}", {"X-Simulate-Failure": "key_1=500"})
    assert r.json()["metadata"]["key_id"] == "key_2"


def test_all_keys_fail_returns_503_and_no_history(client):
    s = f"s-{uid()}"
    r = chat(client, s, f"sim {uid()}", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    assert client.get(f"/sessions/{s}/messages").status_code == 404


def test_simulation_ignored_when_disabled(client, monkeypatch):
    monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "false")
    r = chat(client, f"s-{uid()}", f"sim {uid()}", {"X-Simulate-Failure": "*=429"})
    assert r.status_code == 200


def test_real_provider_error_triggers_failover(client, monkeypatch):
    real = litellm.completion

    def flaky(**kwargs):
        if kwargs["api_key"] == "test-key-1":
            raise RuntimeError("429 rate limit")
        return real(**kwargs)

    monkeypatch.setattr("app.llm.litellm.completion", flaky)
    r = chat(client, f"s-{uid()}", f"real {uid()}")
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"


def test_custom_system_prompt_persists_per_session(client):
    s = f"s-{uid()}"
    r = chat(client, s, f"hi {uid()}", system_prompt="Answer like a pirate.")
    assert r.status_code == 200
    msgs = client.get(f"/sessions/{s}/messages").json()["messages"]
    assert all(m["role"] != "system" for m in msgs)
