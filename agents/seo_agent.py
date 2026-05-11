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
    data_tabs = [
        "Landing Pages",
        "GBP Performance",
        "Search Console Queries",
        "Product Meta",
    ]
