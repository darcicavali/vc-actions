"""ProductAgent — merchandising & buying strategist.

Reads product performance + returns tabs. Role prompt: prompts/product.md.
"""

from __future__ import annotations

from agents.base import BaseAgent


class ProductAgent(BaseAgent):
    name = "ProductAgent"
    role_prompt_file = "product.md"
    data_tabs = [
        "Product by Type",
        "Product by Vendor",
        "All Products",
        "Returns",
    ]
