"""SEOAgent — organic search + local SEO strategist.

Reads landing-page traffic + Google Business Profile tabs from the dashboard
sheet. Shopify product-meta and Search Console queries are deferred until
the dashboard exposes them as sheet tabs (or a dedicated client is wired in).
Role prompt: prompts/seo.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class SEOAgent(BaseAgent):
    name = "SEOAgent"
    role_prompt_file = "seo.md"
    # SEO recommendations follow well-known playbooks (title tag fixes,
    # content gap analysis, local listings hygiene) — pattern work where
    # Haiku performs well at ~1/3 the cost.
    preferred_model = "claude-haiku-4-5"
    data_tabs = [
        "Landing Pages",
        "GBP Performance",
        "Search Console Queries",
        "Product Meta",
        # Organic/site-funnel signals, absorbed from the retired FunnelAgent
        # (2026-05-29): how organic landings engage and convert, by device.
        "Device Breakdown",
    ]
