"""Conversation history persisted to SQLite.

Each row is one Anthropic message (user / assistant / tool result), stored
as the JSON-serialized `content` block list so we round-trip back to the
API verbatim — including tool_use blocks, which the API requires verbatim
for the next turn.

Design notes:

- Single conversation per user keyed by `conversation_id` (default
  "darci"). Multi-user is out of scope.
- The DB lives at chat/data/conversations.db by default. Override via the
  VC_CHAT_DB env var (Streamlit and Telegram both read this).
- We keep the FULL transcript on disk but only feed the most recent
  ~50 turns (or whatever the brain selects) into the API. Long-term
  pruning / compaction can come later — at ~$0.01/turn cached, even
  500-turn transcripts cost <$5 to replay.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "conversations.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_id ON messages(conversation_id, id);
"""


class ConversationStore:
    """Thread-safe SQLite-backed message log.

    Streamlit reruns the script on every interaction, so the store is
    constructed fresh per request — keep init cheap (one CREATE IF NOT
    EXISTS) and connections short-lived.
    """

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            env_path = os.environ.get("VC_CHAT_DB")
            db_path = Path(env_path) if env_path else DEFAULT_DB_PATH
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # SQLite write serialization — we never have heavy concurrency
        # (one user, two transports), but Streamlit + Telegram could write
        # at the same instant if Darci uses both, and SQLite needs a
        # single-writer guarantee.
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def append(self, conversation_id: str, role: str, content: Any) -> int:
        """Append one message. `content` is whatever the API expects:
        a string for plain user/assistant text, or a list of content
        blocks (tool_use, tool_result, text). Returned id is the rowid.
        """
        if role not in {"user", "assistant"}:
            raise ValueError(f"role must be user|assistant, got {role}")
        payload = json.dumps(content, default=str)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, role, payload, time.time()),
            )
            return cur.lastrowid

    def load_recent(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict]:
        """Return the most recent `limit` messages oldest-first, in the
        exact shape the Anthropic Messages API expects: `[{role, content}]`.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content_json FROM messages "
                "WHERE conversation_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        # Reverse to oldest-first.
        msgs: list[dict] = []
        for row in reversed(rows):
            try:
                content = json.loads(row["content_json"])
            except json.JSONDecodeError:
                continue
            msgs.append({"role": row["role"], "content": content})
        return _drop_orphaned_tool_results(msgs)

    def reset(self, conversation_id: str) -> int:
        """Delete every message for a conversation. Returns rows deleted.
        Use sparingly — there's no undo. Surfaced via the /reset slash
        command in both transports.
        """
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            return cur.rowcount


def _drop_orphaned_tool_results(messages: list[dict]) -> list[dict]:
    """If we truncated history mid-tool-call, the first surviving message
    might be a user-role tool_result block whose matching tool_use was
    cut off. The API rejects orphan tool_result blocks. Drop them until
    we land on a clean boundary.
    """
    while messages:
        first = messages[0]
        if first["role"] != "user":
            return messages
        content = first["content"]
        if isinstance(content, str):
            return messages
        if not any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in content
        ):
            return messages
        messages = messages[1:]
    return messages
