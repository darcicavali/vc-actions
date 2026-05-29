"""AdsAgent — paid media strategist.

Reads the Meta Ads sheet tabs and hands them to Claude. The role prompt
(prompts/ads.md) tells Claude how to reason about the funnel.
"""

from __future__ import annotations

from agents.base import BaseAgent


class AdsAgent(BaseAgent):
    name = "AdsAgent"
    role_prompt_file = "ads.md"
    data_tabs = [
        "Meta Ads Summary",
        "Meta Ads by Campaign",
        "Meta Ads by Ad Set",
        "Meta Ads by Ad",
        "Meta Ads Demographics",
        # Paid-funnel signals, absorbed from the retired FunnelAgent
        # (2026-05-29): judge whether paid traffic converts after the click.
        "Weekly Summary",
        "Funnel by Source",
    ]


# Kept for backward compatibility with the integration test.
DATA_TABS = AdsAgent.data_tabs
