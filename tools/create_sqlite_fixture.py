#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    output = Path("tmp/fixture.db")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(output))
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE chat_history (
      id INTEGER PRIMARY KEY,
      user_message TEXT,
      ai_response TEXT,
      agent_type TEXT,
      timestamp TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE agent_task (
      id INTEGER PRIMARY KEY,
      title TEXT,
      status TEXT,
      assigned_agent TEXT,
      updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE xiaobian_profile (
      id INTEGER PRIMARY KEY,
      profile_key TEXT,
      profile_value TEXT,
      updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE dispatcher_rule (
      id INTEGER PRIMARY KEY,
      pattern TEXT,
      target_agent TEXT,
      source TEXT,
      updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE agent_signal (
      id INTEGER PRIMARY KEY,
      agent_key TEXT,
      signal TEXT,
      source TEXT,
      weight REAL,
      updated_at TEXT
    )
    """)

    cur.executemany(
        "INSERT INTO chat_history (id, user_message, ai_response, agent_type, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "hello", "world", "general", now),
            (2, "status", "ok", "engineer", now),
            (3, "draft", "done", "xiaobian", now),
        ],
    )
    cur.executemany(
        "INSERT INTO agent_task (id, title, status, assigned_agent, updated_at) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "verify", "completed", "engineer", now),
            (2, "sync", "running", "researcher", now),
        ],
    )
    cur.executemany(
        "INSERT INTO xiaobian_profile (id, profile_key, profile_value, updated_at) VALUES (?, ?, ?, ?)",
        [
            (1, "tone", "mature", now),
            (2, "locale", "zh-TW", now),
        ],
    )
    cur.executemany(
        "INSERT INTO dispatcher_rule (id, pattern, target_agent, source, updated_at) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "video", "xiaobian", "seed", now),
            (2, "db", "engineer", "seed", now),
        ],
    )
    cur.executemany(
        "INSERT INTO agent_signal (id, agent_key, signal, source, weight, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "engineer", "error", "seed", 0.8, now),
            (2, "xiaobian", "video", "seed", 0.6, now),
        ],
    )

    conn.commit()
    conn.close()
    print(f"fixture_db={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
