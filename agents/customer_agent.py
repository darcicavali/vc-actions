"""CustomerAgent — CRM / lifecycle specialist.

Reads customer segment + retention tabs. Role prompt: prompts/customer.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class CustomerAgent(BaseAgent):
    name = "CustomerAgent"
    role_prompt_file = "customer.md"
    data_tabs = [
        "All Customers",
        "Seg Special",
        "Seg Recency",
        "Retention Summary",
        "Retention Detail",
        "Customer Rankings Online",
        "Customer Rankings POS",
    ]
