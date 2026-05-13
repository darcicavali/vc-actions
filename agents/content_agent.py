"""ContentAgent — organic Instagram strategist.

Reads IG performance tabs. Role prompt: prompts/content.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class ContentAgent(BaseAgent):
    name = "ContentAgent"
    role_prompt_file = "content.md"
    # Organic IG analysis is pattern-matching ("which post types worked",
    # "what to post next week") — well within Haiku's range at ~1/3 the cost.
    preferred_model = "claude-haiku-4-5"
    data_tabs = [
        "IG Summary",
        "IG Posts",
        "IG Content Types",
    ]
