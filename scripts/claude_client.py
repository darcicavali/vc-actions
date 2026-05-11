"""Thin Anthropic API wrapper.

Returns both text and usage so callers can write to the Runtime Log without
re-parsing. Strips common ```json fences so downstream JSON parse is clean.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic


PRICING_PER_MTOK = {
    # Claude Sonnet 4.5 list pricing (USD per 1M tokens).
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    # Default fallback if model unknown.
    "_default": {"input": 3.0, "output": 15.0},
}


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass
class ClaudeResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def cost_usd(self) -> float:
        rate = PRICING_PER_MTOK.get(self.model, PRICING_PER_MTOK["_default"])
        return (
            self.input_tokens * rate["input"] / 1_000_000
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
    """Wraps anthropic.Anthropic. Single method: complete(prompt) -> ClaudeResponse."""

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> ClaudeResponse:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate text blocks (the SDK returns a list of content blocks).
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
            model=self.model,
        )


def parse_json_response(raw_text: str) -> dict:
    """Strip code fences and json.loads. Raises ValueError on parse failure."""
    cleaned = strip_json_fences(raw_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude response was not valid JSON: {e}\nRaw: {raw_text[:500]}")
