"""会话生命周期与持久化清理。"""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.config.settings import settings
from app.utils.agent_trace import resolve_trace_file


SESSION_TABLE = "app_chat_sessions"


def resolve_memory_db_path(db_path: str | Path | None = None) -> Path:
    """统一解析记忆数据库路径，保证 API 与 checkpointer 写入同一个 SQLite。"""
    resolved = Path(db_path or settings.memory_db_path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _now_ms() -> int:
    return int(time.time() * 1000)


def _quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'


def _build_title(message: str | None) -> str:
    text = (message or "").strip()
    if not text:
        return "新的冒险"
    return text[:24]


def _build_preview(message: str | None, reply: str | None) -> str:
    text = (reply or message or "").strip()
    return text[:120]


async def ensure_session_table(db_path: str | Path | None = None) -> None:
    """用一张轻量元数据表记录会话入口，不介入 LangGraph 的官方 checkpoint 表。"""
    db_file = resolve_memory_db_path(db_path)
    async with aiosqlite.connect(str(db_file)) as conn:
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SESSION_TABLE} (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                preview TEXT NOT NULL DEFAULT '',
                message_count INTEGER NOT NULL DEFAULT 0,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            )
            """
        )
        await conn.commit()


async def create_chat_session(title: str | None = None, db_path: str | Path | None = None) -> dict:
    """创建一个空白会话 ID，让前端显式切到干净的 thread。"""
    await ensure_session_table(db_path)
    now = _now_ms()
    session_id = str(uuid4())
    resolved_title = title.strip() if title and title.strip() else "新的冒险"
    db_file = resolve_memory_db_path(db_path)

    async with aiosqlite.connect(str(db_file)) as conn:
        await conn.execute(
            f"""
            INSERT INTO {SESSION_TABLE}(id, title, preview, message_count, created_at_ms, updated_at_ms)
            VALUES (?, ?, '', 0, ?, ?)
            """,
            (session_id, resolved_title, now, now),
        )
        await conn.commit()

    return {
        "id": session_id,
        "title": resolved_title,
        "preview": "",
        "messageCount": 0,
        "createdAt": now,
        "lastMessageAt": now,
    }


async def touch_chat_session(
    *,
    session_id: str,
    message: str | None,
    reply: str | None,
    db_path: str | Path | None = None,
) -> None:
    """在完成一轮交互后更新会话摘要，避免历史页依赖 trace 或 checkpoint 内部结构。"""
    await ensure_session_table(db_path)
    now = _now_ms()
    db_file = resolve_memory_db_path(db_path)

    async with aiosqlite.connect(str(db_file)) as conn:
        cursor = await conn.execute(
            f"SELECT title, message_count FROM {SESSION_TABLE} WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()

        preview = _build_preview(message, reply)
        if row is None:
            await conn.execute(
                f"""
                INSERT INTO {SESSION_TABLE}(id, title, preview, message_count, created_at_ms, updated_at_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, _build_title(message), preview, 1 if message else 0, now, now),
            )
        else:
            title, message_count = row
            next_title = _build_title(message) if title == "新的冒险" and message else title
            await conn.execute(
                f"""
                UPDATE {SESSION_TABLE}
                SET title = ?, preview = ?, message_count = ?, updated_at_ms = ?
                WHERE id = ?
                """,
                (next_title, preview, int(message_count) + (1 if message else 0), now, session_id),
            )

        await conn.commit()


async def list_chat_sessions(db_path: str | Path | None = None) -> list[dict]:
    """按最近活动时间列出会话；空会话也会显示，方便刚创建后继续进入。"""
    await ensure_session_table(db_path)
    db_file = resolve_memory_db_path(db_path)

    async with aiosqlite.connect(str(db_file)) as conn:
        cursor = await conn.execute(
            f"""
            SELECT id, title, preview, message_count, created_at_ms, updated_at_ms
            FROM {SESSION_TABLE}
            ORDER BY updated_at_ms DESC
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()

    return [
        {
            "id": row[0],
            "title": row[1],
            "preview": row[2],
            "messageCount": row[3],
            "createdAt": row[4],
            "lastMessageAt": row[5],
        }
        for row in rows
    ]


async def purge_chat_session_data(session_id: str, db_path: str | Path | None = None) -> dict[str, int]:
    """按会话 ID 清理所有持久化记录，避免旧 thread、派生记忆和 trace 互相污染。"""
    db_file = resolve_memory_db_path(db_path)
    deleted_rows = 0

    async with aiosqlite.connect(str(db_file)) as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        await cursor.close()

        for table in tables:
            column_cursor = await conn.execute(f"PRAGMA table_info({_quote_identifier(table)})")
            columns = {row[1] for row in await column_cursor.fetchall()}
            await column_cursor.close()

            if table == SESSION_TABLE:
                result = await conn.execute(
                    f"DELETE FROM {SESSION_TABLE} WHERE id = ?",
                    (session_id,),
                )
            elif "thread_id" in columns:
                result = await conn.execute(
                    f"DELETE FROM {_quote_identifier(table)} WHERE thread_id = ?",
                    (session_id,),
                )
            elif "session_id" in columns:
                result = await conn.execute(
                    f"DELETE FROM {_quote_identifier(table)} WHERE session_id = ?",
                    (session_id,),
                )
            else:
                continue

            deleted_rows += result.rowcount if result.rowcount > 0 else 0

        await conn.commit()

    trace_file = resolve_trace_file(session_id)
    deleted_trace_files = 0
    if trace_file.exists():
        trace_file.unlink()
        deleted_trace_files = 1

    return {"deletedRows": deleted_rows, "deletedTraceFiles": deleted_trace_files}
