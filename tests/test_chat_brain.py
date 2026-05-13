"""Tests for chat.brain — full conversation turn against a fake
Anthropic client that conforms to the slice of the SDK ChatBrain uses.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from chat.brain import (
    ChatBrain,
    TextDelta,
    ToolCallEnded,
    ToolCallStarted,
    TurnEnded,
)
from chat.memory import ConversationStore


# ---- fake Anthropic client --------------------------------------------


class _FakeStream:
    """Mimics the context manager returned by client.messages.stream().
    `text_stream` is iterated for side effects only; `get_final_message()`
    returns the queued response."""

    def __init__(self, response):
        self._response = response
        self.text_stream = iter([])  # brain doesn't depend on per-token deltas

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_final_message(self):
        return self._response


class _FakeMessages:
    def __init__(self):
        self._queue: list[Any] = []
        self.calls: list[dict] = []

    def queue(self, response) -> None:
        self._queue.append(response)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self._queue:
            raise AssertionError("FakeMessages.stream called but queue is empty")
        return _FakeStream(self._queue.pop(0))


class FakeAnthropicClient:
    def __init__(self):
        self.messages = _FakeMessages()


def _make_response(
    *,
    text: str | None = None,
    tool_calls: list[dict] | None = None,
    stop_reason: str = "end_turn",
    model: str = "claude-opus-4-7",
):
    """Build a Message-like object with .content / .usage / .stop_reason
    matching what the SDK returns. `tool_calls` is a list of
    {name, id, input} dicts that become tool_use blocks."""
    blocks: list[Any] = []
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))
    for tc in tool_calls or []:
        blocks.append(
            SimpleNamespace(type="tool_use", id=tc["id"], name=tc["name"], input=tc.get("input", {}))
        )
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return SimpleNamespace(
        content=blocks,
        usage=usage,
        stop_reason=stop_reason,
        model=model,
    )


# ---- fixtures ---------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(tmp_path / "chat.db")


@pytest.fixture
def brain(sheets, store):
    """Sheets fixture comes from tests/conftest.py."""
    client = FakeAnthropicClient()
    b = ChatBrain(
        client,
        sheets,
        store,
        transport="test",
        conversation_id="t1",
    )
    return b


# ---- tests ------------------------------------------------------------


def test_simple_turn_without_tools_persists_user_and_assistant(brain, store):
    brain.client.messages.queue(_make_response(text="hello back"))
    events = list(brain.handle_message("hello"))

    text_deltas = [e for e in events if isinstance(e, TextDelta)]
    turn_endeds = [e for e in events if isinstance(e, TurnEnded)]
    assert text_deltas[0].text == "hello back"
    assert len(turn_endeds) == 1
    assert turn_endeds[0].iterations == 1
    assert turn_endeds[0].cost_usd > 0

    msgs = store.load_recent("t1")
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"
    assert msgs[1]["role"] == "assistant"


def test_turn_with_one_tool_call_runs_dispatch_then_continues(brain, store, sheets):
    sheets.ensure_tab("MyTab", ["a", "b"])
    sheets.append_row("MyTab", ["x", "y"])

    # First response: model wants to call read_sheet_tab.
    brain.client.messages.queue(
        _make_response(
            tool_calls=[{"id": "tu_1", "name": "read_sheet_tab", "input": {"tab_name": "MyTab"}}],
            stop_reason="tool_use",
        )
    )
    # Second response: model gives final text answer.
    brain.client.messages.queue(_make_response(text="MyTab has one row"))

    events = list(brain.handle_message("what's in MyTab?"))
    started = [e for e in events if isinstance(e, ToolCallStarted)]
    ended = [e for e in events if isinstance(e, ToolCallEnded)]
    text = [e for e in events if isinstance(e, TextDelta)]

    assert started[0].name == "read_sheet_tab"
    assert ended[0].is_error is False
    assert text[-1].text == "MyTab has one row"

    # The store should now contain: user, assistant(tool_use),
    # user(tool_result), assistant(text). 4 messages.
    msgs = store.load_recent("t1")
    assert len(msgs) == 4
    assert msgs[0]["content"] == "what's in MyTab?"
    # The tool_use block should be in the assistant's content.
    assistant_blocks = msgs[1]["content"]
    assert any(b.get("type") == "tool_use" for b in assistant_blocks)
    # Tool_result must come back as a user message with matching tool_use_id.
    tool_result_block = msgs[2]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "tu_1"


def test_max_iterations_cap_stops_runaway_loop(brain, store):
    # Always reply with a tool_use; brain should bail at MAX_TOOL_ITERATIONS.
    from chat.brain import MAX_TOOL_ITERATIONS

    for i in range(MAX_TOOL_ITERATIONS + 2):
        brain.client.messages.queue(
            _make_response(
                tool_calls=[
                    {
                        "id": f"tu_{i}",
                        "name": "read_action_plan",
                        "input": {},
                    }
                ],
                stop_reason="tool_use",
            )
        )
    events = list(brain.handle_message("loop forever"))
    turn_ended = [e for e in events if isinstance(e, TurnEnded)][0]
    assert turn_ended.stopped_early_reason == "max_iterations"
    assert turn_ended.iterations == MAX_TOOL_ITERATIONS


def test_write_tool_call_logs_to_bot_actions_tab(brain, store, sheets):
    brain.client.messages.queue(
        _make_response(
            tool_calls=[
                {
                    "id": "tu_1",
                    "name": "add_lesson",
                    "input": {
                        "agent_target": "AdsAgent",
                        "category": "hard_rule",
                        "lesson": "no TikTok",
                    },
                }
            ],
            stop_reason="tool_use",
        )
    )
    brain.client.messages.queue(_make_response(text="Got it."))

    list(brain.handle_message("never recommend TikTok"))

    audit_rows = sheets.read_tab("Bot Actions")
    assert len(audit_rows) == 1
    assert audit_rows[0]["tool_name"] == "add_lesson"
    assert audit_rows[0]["transport"] == "test"
    assert audit_rows[0]["requires_confirmation"] == "no"


def test_read_tool_call_does_NOT_log_to_bot_actions(brain, store, sheets):
    """Audit log is for writes only — it'd be noise to log every read."""
    sheets.ensure_tab("Anything", ["x"])
    brain.client.messages.queue(
        _make_response(
            tool_calls=[
                {"id": "tu_1", "name": "read_sheet_tab", "input": {"tab_name": "Anything"}}
            ],
            stop_reason="tool_use",
        )
    )
    brain.client.messages.queue(_make_response(text="ok"))

    list(brain.handle_message("read it"))
    assert sheets.read_tab("Bot Actions") == []


def test_system_prompt_has_cache_control_breakpoint(brain):
    """Verify the cacheable prefix structure — last system block must
    carry cache_control so the prefix caches across turns."""
    blocks = brain._system_blocks()
    assert len(blocks) == 2
    assert blocks[0].get("cache_control") is None  # role prompt: no marker
    assert blocks[-1].get("cache_control") == {"type": "ephemeral"}


def test_handle_message_empty_string_is_a_noop(brain, store):
    events = list(brain.handle_message("   "))
    assert events == []
    assert store.load_recent("t1") == []


def test_confirmation_gate_blocks_destructive_tool(brain, store, sheets, monkeypatch):
    """When a tool is in DESTRUCTIVE_TOOLS, the brain returns a
    'NOT EXECUTED' tool_result rather than running it, and logs the
    block to the audit tab."""
    from chat import guardrails, tools as tools_module

    monkeypatch.setattr(
        guardrails, "DESTRUCTIVE_TOOLS", frozenset({"read_action_plan"})
    )

    brain.client.messages.queue(
        _make_response(
            tool_calls=[{"id": "tu_1", "name": "read_action_plan", "input": {}}],
            stop_reason="tool_use",
        )
    )
    brain.client.messages.queue(_make_response(text="Awaiting your confirmation."))

    events = list(brain.handle_message("show me the plan"))
    ended = [e for e in events if isinstance(e, ToolCallEnded)][0]
    assert "confirmation" in ended.result_summary.lower()

    # Audit tab gets the BLOCKED row.
    audit_rows = sheets.read_tab("Bot Actions")
    assert len(audit_rows) == 1
    assert audit_rows[0]["requires_confirmation"] == "yes"
    assert audit_rows[0]["confirmed"] == "no"
    assert "BLOCKED" in audit_rows[0]["result_summary"]
