import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.services.session_store import (
    create_chat_session,
    list_chat_sessions,
    purge_chat_session_data,
    touch_chat_session,
)
from app.utils.agent_trace import resolve_trace_file


class SessionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_metadata_is_created_and_updated(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite3"

            session = await create_chat_session(db_path=db_path)
            await touch_chat_session(
                session_id=session["id"],
                message="调查洞口",
                reply="你发现了新鲜脚印。",
                db_path=db_path,
            )

            sessions = await list_chat_sessions(db_path=db_path)

        self.assertEqual(session["id"], sessions[0]["id"])
        self.assertEqual("调查洞口", sessions[0]["title"])
        self.assertEqual("你发现了新鲜脚印。", sessions[0]["preview"])
        self.assertEqual(1, sessions[0]["messageCount"])

    async def test_purge_session_removes_checkpoint_memory_and_trace_only_for_target(self):
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite3"
            trace_dir = Path(temp_dir) / "agent_traces"
            target_trace = resolve_trace_file("target", trace_dir)
            other_trace = resolve_trace_file("other", trace_dir)
            target_trace.write_text("target trace", encoding="utf-8")
            other_trace.write_text("other trace", encoding="utf-8")

            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE checkpoints(thread_id TEXT, checkpoint TEXT)")
            conn.execute("CREATE TABLE writes(thread_id TEXT, value TEXT)")
            conn.execute("CREATE TABLE episodic_memory(session_id TEXT, payload_json TEXT)")
            conn.execute("CREATE TABLE app_chat_sessions(id TEXT PRIMARY KEY, title TEXT, preview TEXT, message_count INTEGER, created_at_ms INTEGER, updated_at_ms INTEGER)")
            for value in ("target", "other"):
                conn.execute("INSERT INTO checkpoints VALUES (?, ?)", (value, "{}"))
                conn.execute("INSERT INTO writes VALUES (?, ?)", (value, "{}"))
                conn.execute("INSERT INTO episodic_memory VALUES (?, ?)", (value, "{}"))
                conn.execute("INSERT INTO app_chat_sessions VALUES (?, 't', '', 0, 1, 1)", (value,))
            conn.commit()
            conn.close()

            with patch("app.services.session_store.resolve_trace_file", lambda session_id: resolve_trace_file(session_id, trace_dir)):
                result = await purge_chat_session_data("target", db_path=db_path)

            conn = sqlite3.connect(db_path)
            target_count = sum(
                conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = 'target'").fetchone()[0]
                for table, column in (
                    ("checkpoints", "thread_id"),
                    ("writes", "thread_id"),
                    ("episodic_memory", "session_id"),
                    ("app_chat_sessions", "id"),
                )
            )
            other_count = sum(
                conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = 'other'").fetchone()[0]
                for table, column in (
                    ("checkpoints", "thread_id"),
                    ("writes", "thread_id"),
                    ("episodic_memory", "session_id"),
                    ("app_chat_sessions", "id"),
                )
            )
            conn.close()

            self.assertEqual(0, target_count)
            self.assertEqual(4, other_count)
            self.assertEqual({"deletedRows": 4, "deletedTraceFiles": 1}, result)
            self.assertFalse(target_trace.exists())
            self.assertTrue(other_trace.exists())


if __name__ == "__main__":
    unittest.main()
