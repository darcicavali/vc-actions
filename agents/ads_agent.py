"""AdsAgent — paid media strategist.

Per v4 spec: pulls the Meta Ads sheet tabs and hands them to Claude. The
focus tabs are listed in DATA_TABS. The role prompt (prompts/ads.md) tells
Claude how to reason about the funnel.
"""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


# Tabs read by the agent. Names match the dashboard sheet (vc-dashboard).
# Missing tabs degrade to an empty list rather than failing the run.
DATA_TABS: list[str] = [
    "Meta Ads Summary",
    "Meta Ads by Campaign",
    "Meta Ads by Ad Set",
    "Meta Ads by Ad",
    "Meta Ads Demographics",
]


class AdsAgent(BaseAgent):
    name = "AdsAgent"
    role_prompt_file = "ads.md"

    def gather_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for tab in DATA_TABS:
            try:
                out[tab] = self.sheets.read_tab(tab)
            except Exception as e:
                # A missing or unreadable tab is data quality info, not a hard fail.
                out[tab] = {"error": f"{type(e).__name__}: {e}"}
        return out
