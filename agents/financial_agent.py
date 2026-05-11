"""FinancialAgent — boutique CFO.

Reads financial summary tabs. Role prompt: prompts/financial.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class FinancialAgent(BaseAgent):
    name = "FinancialAgent"
    role_prompt_file = "financial.md"
    data_tabs = [
        "Financial Summary",
        "Monthly Financial",
        "Returns",
        "COGS",
        "Margin Trends",
    ]
