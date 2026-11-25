"""SQLite storage for sessions and messages (stdlib sqlite3, no ORM)."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    system_prompt TEXT,
    created_at TEXT NOT NULL
);
"""


def db_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    return url.split("sqlite:///", 1)[1] if url.startswith("sqlite:///") else url


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    folder = os.path.dirname(os.path.abspath(db_path()))
    os.makedirs(folder, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)


def ping() -> bool:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def get_system_prompt(session_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return row["system_prompt"] if row else None


def get_history(session_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        item = {"role": r["role"], "content": r["content"]}
        if r["metadata"]:
            item["metadata"] = json.loads(r["metadata"])
        out.append(item)
    return out


def add_exchange(session_id: str, user_text: str, reply: str, metadata: dict,
                 system_prompt: str | None) -> None:
    """Persist a successful turn atomically. Failed requests never reach this."""
    now = _now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, system_prompt, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt)",
            (session_id, system_prompt, now),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) "
            "VALUES (?, 'user', ?, NULL, ?)",
            (session_id, user_text, now),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) "
            "VALUES (?, 'assistant', ?, ?, ?)",
            (session_id, reply, json.dumps(metadata), _now()),
        )
