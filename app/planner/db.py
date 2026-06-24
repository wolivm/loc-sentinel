"""SQLite store for tickets, translation units, and the audit log.

A thin repository boundary (DECISIONS #10): SQLite now, but nothing here leaks
sqlite specifics to callers, so swapping to Postgres is a config change. The
translation engine itself stays stateless — only the planner has state.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT,                 -- where it came from (crowdin webhook / slack / cli)
    payload TEXT,                -- JSON blob of the originating event
    target_lang TEXT,
    assignee TEXT,
    requester TEXT,
    confidence_summary TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    crowdin_string_id TEXT,
    key TEXT,
    source_en TEXT,
    context TEXT,
    proposed_target TEXT,
    final_target TEXT,
    status TEXT NOT NULL,        -- proposed | approved | edited | rejected
    confidence TEXT,
    confidence_score REAL,
    qa_flags TEXT,               -- JSON
    tm_origin TEXT,
    provenance TEXT,             -- JSON: glossary applied, translation origin, etc.
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity TEXT NOT NULL,        -- e.g. ticket:T12 / unit:U34
    from_state TEXT,
    to_state TEXT,
    actor TEXT,
    detail TEXT,
    at TEXT NOT NULL
);

-- Dedupe table for idempotent webhook handling (LIMITATIONS: webhook replay).
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    at TEXT NOT NULL
);
"""

_conn: sqlite3.Connection | None = None


def get_conn(path: Path | None = None) -> sqlite3.Connection:
    global _conn
    if _conn is None or path is not None:
        target = path or DB_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(_SCHEMA)
        conn.commit()
        if path is not None:
            return conn
        _conn = conn
    return _conn


def init_db(path: Path | None = None) -> None:
    get_conn(path)
