"""SQLite-backed checkpointer for persisting conversation state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any, Optional


class Checkpointer:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        if not self._db_path.is_absolute():
            self._db_path = Path.cwd() / self._db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), check_same_thread=False)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_memory (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def save(self, key: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO conversation_memory(session_id, state_json, updated_at)
                    VALUES(?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(session_id)
                    DO UPDATE SET state_json=excluded.state_json, updated_at=CURRENT_TIMESTAMP
                    """,
                    (key, payload),
                )
                conn.commit()

    def load(self, key: str) -> Optional[dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "SELECT state_json FROM conversation_memory WHERE session_id = ?",
                    (key,),
                )
                row = cursor.fetchone()
        if not row:
            return None

        try:
            data = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

        return data if isinstance(data, dict) else None

