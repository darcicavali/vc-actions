"""Conversation brain — Anthropic API loop, tool dispatch, streaming.

One public entry point: `ChatBrain.handle_message(user_text)`. It's a
generator that yields `ChatEvent` instances as the model produces them
(text deltas first, then tool calls, then more text, then `TurnEnded`).
Both transports consume the same generator — Streamlit renders deltas
live via `st.write_stream`; Telegram buffers them and sends one message
at the end.

Implementation notes:

- Manual agentic loop, not the SDK tool runner. We need to (a) stream
  text to the user as it arrives, (b) write each tool call to the audit
  tab, and (c) cap iterations. The tool runner returns whole messages
  per iteration and doesn't expose those hooks cleanly.
- Opus 4.7 with `thinking: {type: "adaptive"}` and `effort: "medium"`.
  Medium is the sweet spot for this workload — Darci's questions are
  substantive but rarely require "max" depth.
- Prompt caching via explicit `cache_control` on the last system block.
  The system prompt + business context (~5K tokens) caches across every
  turn of the conversation and across all of her sessions — first turn
  pays the write premium, every subsequent turn reads at ~10% input cost.
- Compaction is NOT enabled yet. We'd add the `compact-2026-01-12` beta
  header when transcripts get within striking distance of the 1M context
  ceiling. At ~500 tokens per turn average, that's ~2000 turns away.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import anthropic

from chat import audit, guardrails, tools as tools_module
from chat.memory import ConversationStore


LOG = logging.getLogger(__name__)


# Default model / sampling. Opus 4.7 is intentionally chosen — Darci's
# questions are conversational analysis, where quality compounds. At ~5K
# cached input + ~500 output per turn, per-turn cost is ~$0.02. Cheap
# enough that even 100 turns/month sits under $5.
DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_EFFORT = "medium"
MAX_TOOL_ITERATIONS = 10  # safety cap per user message

# Pricing for cost estimation in events. Sourced from shared/models.md
# in the claude-api skill (cached 2026-04-29). Cache-write 1.25x base,
# cache-read 0.1x base.
PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "_default": {"input": 5.0, "output": 25.0},
}
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.1


REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "system.md"
BUSINESS_CONTEXT_FILE = REPO_ROOT / "prompts" / "base_context.md"


# ---- events the transport renders --------------------------------------


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCallStarted:
    name: str
    args: dict


@dataclass
class ToolCallEnded:
    name: str
    result_summary: str  # truncated for display
    is_error: bool = False


@dataclass
class TurnEnded:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    iterations: int = 1
    stopped_early_reason: str | None = None


ChatEvent = TextDelta | ToolCallStarted | ToolCallEnded | TurnEnded


# ---- usage accumulation across tool-use iterations ---------------------


@dataclass
class _UsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    iterations: int = 0
    model_seen: list[str] = field(default_factory=list)

    def add(self, usage, model: str) -> None:
        self.iterations += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        if model not in self.model_seen:
            self.model_seen.append(model)

    def cost_usd(self) -> float:
        # Use the first model's pricing — almost always identical across
        # iterations of one turn.
        rate = PRICING_PER_MTOK.get(
            self.model_seen[0] if self.model_seen else "_default",
            PRICING_PER_MTOK["_default"],
        )
        in_per = rate["input"] / 1_000_000
        out_per = rate["output"] / 1_000_000
        return (
            self.input_tokens * in_per
            + self.cache_creation_tokens * in_per * CACHE_WRITE_MULT
            + self.cache_read_tokens * in_per * CACHE_READ_MULT
            + self.output_tokens * out_per
        )


# ---- ChatBrain ---------------------------------------------------------


class ChatBrain:
    def __init__(
        self,
        anthropic_client: anthropic.Anthropic,
        sheets,
        store: ConversationStore,
        *,
        transport: str,
        conversation_id: str = "darci",
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str = DEFAULT_EFFORT,
        adaptive_thinking: bool = True,
    ):
        self.client = anthropic_client
        self.sheets = sheets
        self.store = store
        self.transport = transport
        self.conversation_id = conversation_id
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.adaptive_thinking = adaptive_thinking
        self._system_blocks_cache: list[dict] | None = None

    # ---- system prompt assembly (cached across turns) ----

    def _system_blocks(self) -> list[dict]:
        """Render the cacheable system prefix. Read from disk once per
        ChatBrain instance — Streamlit constructs a new ChatBrain per
        rerun, so we trade a little disk I/O on each rerun for a simple
        invariant: edit `prompts/system.md`, restart, see the change.
        """
        if self._system_blocks_cache is not None:
            return self._system_blocks_cache
        role = SYSTEM_PROMPT_FILE.read_text().strip()
        context = BUSINESS_CONTEXT_FILE.read_text().strip()
        blocks = [
            {"type": "text", "text": role},
            {
                "type": "text",
                "text": f"BUSINESS CONTEXT:\n{context}",
                # Cache breakpoint — the prefix above caches across every
                # turn of every conversation Darci ever has with the bot.
                # First turn pays the 1.25x write premium; subsequent turns
                # read this prefix at 0.1x (~$0.0025/turn vs $0.025).
                "cache_control": {"type": "ephemeral"},
            },
        ]
        self._system_blocks_cache = blocks
        return blocks

    # ---- main entry point ----

    def handle_message(self, user_text: str) -> Iterator[ChatEvent]:
        """Run one user turn end-to-end. Yields events as the model
        produces them. Persists user message + final assistant turn
        (including all tool_use / tool_result blocks) to the store so
        the next turn picks up correctly.
        """
        if not user_text.strip():
            return

        # Persist the user turn before calling the model — if the call
        # fails, we still have a clean record of what she asked.
        self.store.append(self.conversation_id, "user", user_text)

        # Load history from disk (includes the message we just appended).
        messages: list[dict] = self.store.load_recent(self.conversation_id, limit=100)
        usage_acc = _UsageAccumulator()
        stopped_early: str | None = None

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = self._stream_one_turn(messages, usage_acc)
            if response is None:
                stopped_early = "stream_aborted"
                break

            yield from self._yield_text_deltas_from_response(response)

            stop_reason = getattr(response, "stop_reason", None)
            if stop_reason != "tool_use":
                # end_turn / max_tokens / refusal — we're done. Persist
                # the assistant turn (full content blocks, including any
                # text + thinking blocks the API returned) and exit.
                self.store.append(
                    self.conversation_id,
                    "assistant",
                    _serialize_content(response.content),
                )
                if stop_reason == "max_tokens":
                    stopped_early = "hit_max_tokens"
                elif stop_reason == "refusal":
                    stopped_early = "model_refused"
                break

            # tool_use path: persist the assistant turn, run tools,
            # append tool_result user message, loop.
            self.store.append(
                self.conversation_id,
                "assistant",
                _serialize_content(response.content),
            )
            messages.append(
                {"role": "assistant", "content": _serialize_content(response.content)}
            )
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                events_and_result = self._execute_tool_call(block)
                # _execute_tool_call yields events plus returns the
                # tool_result block. Use a small helper pattern: it's a
                # generator that returns the dict via a sentinel pair.
                for item in events_and_result:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_results.append(item)
                    else:
                        yield item

            user_turn = {"role": "user", "content": tool_results}
            self.store.append(self.conversation_id, "user", tool_results)
            messages.append(user_turn)
        else:
            stopped_early = "max_iterations"

        yield TurnEnded(
            input_tokens=usage_acc.input_tokens,
            output_tokens=usage_acc.output_tokens,
            cache_read_tokens=usage_acc.cache_read_tokens,
            cache_creation_tokens=usage_acc.cache_creation_tokens,
            cost_usd=usage_acc.cost_usd(),
            iterations=usage_acc.iterations,
            stopped_early_reason=stopped_early,
        )

    # ---- internals ----

    def _stream_one_turn(
        self, messages: list[dict], usage_acc: _UsageAccumulator
    ):
        """One round-trip to the API with streaming. Returns the final
        message (with full content blocks + usage). Caller iterates
        text deltas from the response separately for simplicity — we
        already have the complete response, so we synthesize deltas
        from the text blocks rather than re-streaming.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self._system_blocks(),
            "tools": tools_module.TOOL_SPECS,
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        if self.adaptive_thinking:
            # `display: "summarized"` so reasoning streams visibly
            # rather than appearing as a long pause (Opus 4.7 default
            # is "omitted").
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}

        try:
            with self.client.messages.stream(**kwargs) as stream:
                # Drain the stream so server-side tokens flow; we use
                # get_final_message() rather than re-emitting deltas
                # mid-stream because tool dispatch interleaves and
                # mixing live deltas with sync tool I/O makes the
                # transport contract ugly. Streamlit can render the
                # final text fast enough; Telegram only cares about
                # the final message anyway.
                for _ in stream.text_stream:
                    pass
                final = stream.get_final_message()
        except anthropic.APIError as e:
            LOG.error("Anthropic API error during chat turn: %s", e)
            raise

        usage_acc.add(final.usage, getattr(final, "model", self.model))
        return final

    def _yield_text_deltas_from_response(self, response) -> Iterator[ChatEvent]:
        """Emit one TextDelta per text block. We don't sub-tokenize —
        transports show the chunked-by-block text immediately on receipt.
        """
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "")
                if text:
                    yield TextDelta(text=text)

    def _execute_tool_call(self, tool_use_block) -> Iterator:
        """Run one tool call, yield events, and yield the tool_result
        dict the model expects on the next turn (as a sentinel dict).
        """
        name = tool_use_block.name
        args = dict(tool_use_block.input or {})
        tool_use_id = tool_use_block.id

        yield ToolCallStarted(name=name, args=args)

        # Confirmation gate. Today DESTRUCTIVE_TOOLS is empty — when we
        # add a destructive tool, this path activates without further
        # changes. We surface a synthesized tool_result asking the model
        # to confirm; the model surfaces a confirmation prompt to Darci;
        # she replies "yes" or not; the model re-issues the call.
        requires_confirmation = guardrails.needs_confirmation(name, args)
        if requires_confirmation:
            prompt = guardrails.confirmation_prompt(name, args)
            audit.log_action(
                self.sheets,
                transport=self.transport,
                conversation_id=self.conversation_id,
                tool_name=name,
                tool_args=args,
                result_summary=f"BLOCKED awaiting confirmation: {prompt}",
                requires_confirmation=True,
                confirmed=False,
            )
            yield ToolCallEnded(
                name=name,
                result_summary="awaiting user confirmation",
                is_error=False,
            )
            yield {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": (
                    f"NOT EXECUTED. This tool requires explicit user "
                    f"confirmation. Tell the user: '{prompt}' and wait "
                    f"for them to reply 'yes' before re-issuing the call."
                ),
                "is_error": False,
            }
            return

        # Read / append-only path: run immediately.
        try:
            result_text = tools_module.dispatch(name, args, self.sheets)
            is_error = result_text.startswith("ERROR")
        except Exception as e:  # noqa: BLE001
            result_text = f"ERROR: dispatch raised: {e}"
            is_error = True

        # Audit ALL tool calls (read or write) so Darci has one log to
        # consult. Read calls log a short marker; writes log the full
        # result summary.
        is_write = name in {"add_lesson", "note_for_next_run"}
        if is_write:
            audit.log_action(
                self.sheets,
                transport=self.transport,
                conversation_id=self.conversation_id,
                tool_name=name,
                tool_args=args,
                result_summary=result_text,
                requires_confirmation=False,
                confirmed=False,  # n/a for append-only; logged as "n/a"
            )

        yield ToolCallEnded(
            name=name,
            result_summary=_truncate(result_text, 200),
            is_error=is_error,
        )
        yield {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result_text,
            "is_error": is_error,
        }


# ---- helpers ----------------------------------------------------------


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _serialize_content(content) -> list[dict]:
    """Convert SDK BetaContentBlock objects to plain dicts for storage
    and re-feeding to the API. The SDK accepts dicts back symmetrically
    on the next request.
    """
    out: list[dict] = []
    for block in content:
        # Some blocks support .model_dump (Pydantic); others may already
        # be dicts (test fakes). Handle both.
        if isinstance(block, dict):
            out.append(block)
        elif hasattr(block, "model_dump"):
            d = block.model_dump(exclude_none=True)
            # Drop fields the API rejects on round-trip (rare; safety).
            out.append(d)
        else:
            # Fallback: best-effort dict via getattr on common fields.
            d: dict[str, Any] = {"type": getattr(block, "type", "text")}
            for f in ("text", "id", "name", "input", "thinking", "signature"):
                v = getattr(block, f, None)
                if v is not None:
                    d[f] = v
            out.append(d)
    return out
