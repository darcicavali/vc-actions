"""ContentAgent — organic Instagram strategist.

Reads IG performance tabs. Role prompt: prompts/content.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class ContentAgent(BaseAgent):
    name = "ContentAgent"
    role_prompt_file = "content.md"
    data_tabs = [
        "IG Summary",
        "IG Posts",
        "IG Content Types",
    ]
