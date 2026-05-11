"""FunnelAgent — conversion / CRO specialist.

Reads funnel + landing-page + device tabs. Role prompt: prompts/funnel.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class FunnelAgent(BaseAgent):
    name = "FunnelAgent"
    role_prompt_file = "funnel.md"
    data_tabs = [
        "Weekly Summary",
        "Landing Pages",
        "Device Breakdown",
        "Funnel by Source",
    ]
