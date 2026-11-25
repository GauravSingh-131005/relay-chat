import { useEffect, useRef, useState } from "react";

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

const newSessionId = () =>
  "s-" + (crypto.randomUUID ? crypto.randomUUID().slice(0, 8) : Math.random().toString(36).slice(2, 10));

const STARTERS = [
  "What is the capital of France?",
  "Explain what an API rate limit is in two sentences.",
  "Give me three names for a coffee shop.",
];

function readableError(status, body) {
  if (status === 503) return "Every provider is unavailable right now. Try again in a moment.";
  if (status === 422) {
    const first = Array.isArray(body?.detail) ? body.detail[0] : null;
    const field = first?.loc?.[first.loc.length - 1];
    if (field === "message") return "Message must be between 1 and 4000 characters.";
    return "That request was not valid. Check your message and try again.";
  }
  return body?.detail && typeof body.detail === "string"
    ? body.detail
    : "Something went wrong on the server. Try again.";
}

function Receipt({ meta }) {
  const live = meta.resolution_source === "LIVE_INFERENCE";
  return (
    <dl className="receipt">
      <div className="cell">
        <dt>Source</dt>
        <dd data-testid="meta-source" className={live ? "src live" : "src cache"}>
          {meta.resolution_source}
        </dd>
      </div>
      <div className="cell">
        <dt>Model</dt>
        <dd data-testid="meta-model">{meta.model}</dd>
      </div>
      <div className="cell">
        <dt>Latency</dt>
        <dd data-testid="meta-latency">{meta.latency_ms} ms</dd>
      </div>
      <div className="cell">
        <dt>Tokens in</dt>
        <dd data-testid="meta-input-tokens">{meta.input_tokens}</dd>
      </div>
      <div className="cell">
        <dt>Tokens out</dt>
        <dd data-testid="meta-output-tokens">{meta.output_tokens}</dd>
      </div>
      <div className="cell route">
        <dt>Route</dt>
        <dd>
          {meta.key_id ? meta.key_id : "cache"}
          {meta.fallback_attempts > 0 && (
            <span className="failover">
              {" "}after {meta.fallback_attempts} failed {meta.fallback_attempts === 1 ? "key" : "keys"}
            </span>
          )}
        </dd>
      </div>
    </dl>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [items, busy]);

  const push = (item) => setItems((prev) => [...prev, { id: crypto.randomUUID?.() || Math.random(), ...item }]);

  async function send(raw) {
    const message = (raw ?? text).trim();
    if (!message || busy) return;
    setText("");
    push({ role: "user", content: message });
    setBusy(true);
    try {
      const body = { session_id: sessionId, message };
      if (systemPrompt.trim()) body.system_prompt = systemPrompt.trim();
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) push({ role: "error", content: readableError(res.status, data) });
      else push({ role: "assistant", content: data.reply, metadata: data.metadata });
    } catch {
      push({ role: "error", content: "Could not reach the server. Check your connection and try again." });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function resetChat() {
    setSessionId(newSessionId());
    setItems([]);
    setText("");
  }

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true" />
          <div>
            <h1>Relay Chat</h1>
            <p>Every reply shows how it was produced.</p>
          </div>
        </div>
        <div className="top-actions">
          <span className="session" title="Current session id">{sessionId}</span>
          <button className="ghost" onClick={() => setShowPrompt((v) => !v)} aria-expanded={showPrompt}>
            System prompt
          </button>
          <button className="ghost" onClick={resetChat}>New chat</button>
        </div>
      </header>

      {showPrompt && (
        <section className="prompt-panel">
          <label htmlFor="sys">Instructions for this session</label>
          <textarea
            id="sys"
            data-testid="system-prompt-input"
            rows={2}
            maxLength={4000}
            placeholder="You are a helpful, concise assistant."
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
          />
        </section>
      )}

      <main className="thread" aria-live="polite">
        {items.length === 0 && (
          <div className="empty">
            <h2>Ask anything to start a conversation.</h2>
            <p>Send the same question twice in a new chat to see a cached reply.</p>
            <div className="starters">
              {STARTERS.map((s) => (
                <button key={s} className="starter" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {items.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="row user"><div className="bubble user">{m.content}</div></div>
          ) : m.role === "error" ? (
            <div key={m.id} className="row"><div className="notice" role="alert">{m.content}</div></div>
          ) : (
            <div key={m.id} className="row">
              <article className="bubble bot" data-testid="assistant-message">
                <p className="reply">{m.content}</p>
                <Receipt meta={m.metadata} />
              </article>
            </div>
          )
        )}

        {busy && (
          <div className="row"><div className="bubble bot typing" aria-label="Waiting for reply"><i /><i /><i /></div></div>
        )}
        <div ref={endRef} />
      </main>

      <footer className="composer">
        <textarea
          ref={inputRef}
          data-testid="chat-input"
          rows={1}
          maxLength={4000}
          placeholder="Write a message. Enter sends, Shift+Enter adds a line."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button className="send" data-testid="send-button" onClick={() => send()} disabled={busy || !text.trim()}>
          Send
        </button>
      </footer>
    </div>
  );
}
