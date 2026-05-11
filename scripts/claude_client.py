"""Thin Anthropic API wrapper.

Returns both text and usage so callers can write to the Runtime Log without
re-parsing. Strips common ```json fences so downstream JSON parse is clean.

Supports prompt caching: pass `system` as a list of text blocks with
`cache_control` on the last stable block. The Anthropic API caches the
prefix (tools + system) for ~5 minutes by default. When 7 specialists run
in sequence, the shared role-prompt + business-context prefix is read from
cache after the first agent, dropping input cost ~90% on the cached span.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic


# USD per 1M tokens. Cache writes cost 1.25x base input, cache reads 0.1x.
# Source: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
PRICING_PER_MTOK = {
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    "_default": {"input": 3.0, "output": 15.0},
}

CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass
class ClaudeResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        rate = PRICING_PER_MTOK.get(self.model, PRICING_PER_MTOK["_default"])
        in_rate = rate["input"] / 1_000_000
        return (
            self.input_tokens * in_rate
            + self.cache_creation_input_tokens * in_rate * CACHE_WRITE_MULTIPLIER
            + self.cache_read_input_tokens * in_rate * CACHE_READ_MULTIPLIER
            + self.output_tokens * rate["output"] / 1_000_000
        )


def strip_json_fences(raw: str) -> str:
    """Remove leading ```json / trailing ``` wrappers if present."""
    s = raw.strip()
    if s.startswith("```"):
        # remove opening fence line
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n", "", s)
    if s.endswith("```"):
        s = re.sub(r"\n```\s*$", "", s)
    return s.strip()


class ClaudeClient:
    """Wraps anthropic.Anthropic. Single method: complete() -> ClaudeResponse."""

    # Observed: successful agent runs produce 1200-1700 output tokens. 2500
    # leaves headroom without inflating per-minute token usage that pushes
    # us into rate-limit territory.
    DEFAULT_MAX_TOKENS = 2500

    def __init__(self, api_key: str, model: str, max_tokens: int = DEFAULT_MAX_TOKENS):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(
        self,
        user_prompt: str,
        *,
        system: list[dict] | str | None = None,
        model: str | None = None,
    ) -> ClaudeResponse:
        """Send a message. `system` may be a string OR a list of text blocks
        (with optional `cache_control` for prompt caching). `model` overrides
        the client default for this call only — used to route lighter agents
        to Haiku without spinning up a second client.
        """
        kwargs: dict = {
            "model": model or self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system is not None:
            kwargs["system"] = system

        resp = self._client.messages.create(**kwargs)
        text_parts = []
        for block in resp.content:
            block_text = getattr(block, "text", None)
            if block_text:
                text_parts.append(block_text)
        text = "".join(text_parts)
        usage = resp.usage
        return ClaudeResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            model=kwargs["model"],
            cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )


def parse_json_response(raw_text: str) -> dict:
    """Strip code fences and json.loads. Raises ValueError on parse failure."""
    cleaned = strip_json_fences(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude response was not valid JSON: {e}\nRaw: {raw_text[:500]}")
