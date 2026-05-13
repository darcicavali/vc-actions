"""Tests for chat.memory.ConversationStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from chat.memory import ConversationStore


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(tmp_path / "test.db")


def test_append_and_load_returns_messages_oldest_first(store):
    store.append("c1", "user", "hello")
    store.append("c1", "assistant", [{"type": "text", "text": "hi"}])
    store.append("c1", "user", "second")

    msgs = store.load_recent("c1")
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["content"] == [{"type": "text", "text": "hi"}]


def test_load_recent_respects_limit(store):
    for i in range(20):
        store.append("c1", "user", f"msg-{i}")
    msgs = store.load_recent("c1", limit=5)
    assert len(msgs) == 5
    # Most-recent 5, oldest-first
    assert [m["content"] for m in msgs] == [f"msg-{i}" for i in range(15, 20)]


def test_conversations_are_isolated(store):
    store.append("c1", "user", "from-c1")
    store.append("c2", "user", "from-c2")
    assert store.load_recent("c1") == [{"role": "user", "content": "from-c1"}]
    assert store.load_recent("c2") == [{"role": "user", "content": "from-c2"}]


def test_reset_clears_only_target_conversation(store):
    store.append("c1", "user", "a")
    store.append("c1", "user", "b")
    store.append("c2", "user", "keep")
    deleted = store.reset("c1")
    assert deleted == 2
    assert store.load_recent("c1") == []
    assert store.load_recent("c2") == [{"role": "user", "content": "keep"}]


def test_orphan_tool_result_at_history_boundary_dropped(store):
    """If we truncate history mid-tool-cycle, the first surviving message
    might be a user-role tool_result with no matching tool_use. The API
    rejects orphans; load_recent must clean them up."""
    # Append many messages so the limit cuts before the tool_use.
    store.append("c1", "user", "old")
    store.append("c1", "assistant", [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}])
    store.append(
        "c1", "user", [{"type": "tool_result", "tool_use_id": "t1", "content": "r"}]
    )
    store.append("c1", "assistant", [{"type": "text", "text": "done"}])
    store.append("c1", "user", "next")

    # Limit=3 keeps the last 3: [tool_result, assistant text, user "next"].
    # The leading tool_result is orphaned and must be dropped.
    msgs = store.load_recent("c1", limit=3)
    assert msgs[0]["role"] == "assistant"  # orphaned tool_result block dropped
    assert msgs[-1]["content"] == "next"


def test_orphan_drop_handles_string_content_user(store):
    """A leading user message with plain string content is never an
    orphan — leave it alone."""
    store.append("c1", "user", "plain text")
    msgs = store.load_recent("c1")
    assert msgs == [{"role": "user", "content": "plain text"}]


def test_invalid_role_rejected(store):
    with pytest.raises(ValueError):
        store.append("c1", "system", "nope")
