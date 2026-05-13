"""Regenerate the baseline prompt packs in `baseline_prompts/`.

Each pack is a self-contained Markdown file Darci pastes into a Claude.ai
conversation to produce one agent's baseline doc. The packs are assembled
from three sources, so they stay in sync automatically when any source
changes:

  1. The agent's role prompt in `prompts/<role>.md`
  2. The shared business context in `prompts/base_context.md`
  3. The agent-specific section asks in `baseline_prompts/sections/<Agent>.md`

Run after editing any of those:

    python -m scripts.build_baseline_prompts
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.config import PROMPTS_DIR, REPO_ROOT


BASELINE_DIR = REPO_ROOT / "baseline_prompts"
SECTIONS_DIR = BASELINE_DIR / "sections"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role_file: str  # in prompts/
    friendly: str  # human-readable name used in the prompt body
    data_tabs: list[str]


# Keep these in sync with each agent's `data_tabs` in agents/*.py.
AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="AdsAgent",
        role_file="ads.md",
        friendly="paid-media strategist (AdsAgent)",
        data_tabs=[
            "Meta Ads Summary",
            "Meta Ads Targeting",
            "Meta Demographics",
        ],
    ),
    AgentSpec(
        name="CustomerAgent",
        role_file="customer.md",
        friendly="CRM & lifecycle specialist (CustomerAgent)",
        data_tabs=[
            "All Customers",
            "Seg Special",
            "Seg Recency",
            "Retention Summary",
            "Retention Detail",
            "Customer Rankings",
            "Monthly Customer Rankings",
        ],
    ),
    AgentSpec(
        name="ProductAgent",
        role_file="product.md",
        friendly="merchandising strategist (ProductAgent)",
        data_tabs=[
            "Product Performance",
            "Inventory Levels",
            "SKU Velocity",
            "Category Mix",
        ],
    ),
    AgentSpec(
        name="ContentAgent",
        role_file="content.md",
        friendly="organic content strategist (ContentAgent)",
        data_tabs=[
            "IG Summary",
            "IG Posts",
            "IG Content Types",
        ],
    ),
    AgentSpec(
        name="FunnelAgent",
        role_file="funnel.md",
        friendly="conversion-funnel analyst (FunnelAgent)",
        data_tabs=[
            "GA4 Sessions",
            "GA4 Conversions",
            "Shopify Checkout Funnel",
        ],
    ),
    AgentSpec(
        name="FinancialAgent",
        role_file="financial.md",
        friendly="financial analyst (FinancialAgent)",
        data_tabs=[
            "Weekly Summary",
            "Monthly Revenue",
            "COGS Tracking",
            "Goal Tracker",
        ],
    ),
    AgentSpec(
        name="SEOAgent",
        role_file="seo.md",
        friendly="organic-search strategist (SEOAgent)",
        data_tabs=[
            "Landing Pages",
            "GBP Performance",
            "Search Console Queries",
            "Product Meta",
        ],
    ),
    AgentSpec(
        name="GoalsAgent",
        role_file="coordinator.md",
        friendly="strategic coordinator / fractional COO (GoalsAgent)",
        data_tabs=[
            "Action Plan (last 12 weeks)",
            "Agent Memos (last 12 weeks, all agents)",
            "Goal Tracker",
            "Weekly Summary",
        ],
    ),
]


TEMPLATE = """# Baseline Build Pack — {agent}

> Generated from `prompts/{role_file}`, `prompts/base_context.md`, and
> `baseline_prompts/sections/{agent}.md`. To update: edit those sources,
> then run `python -m scripts.build_baseline_prompts`.

## How to use this pack

1. Open a new Claude.ai conversation (model: Opus 4.7 or Sonnet 4.6).
2. Copy everything below the `---` line and paste into the conversation.
3. Attach the data files listed at the bottom (export each tab as CSV from
   Google Sheets — File → Download → CSV).
4. Review Claude's response carefully — edit anything that doesn't ring true.
5. Paste each section into the `BASELINE: {agent}` tab as a new row.

---

You are the {friendly} for Vanessa Cavali Boutique. **This is a one-time
baseline build, not a weekly run.** Your task: read full historical data
and produce a curated baseline doc that captures what NORMAL looks like
for this business — so the weekly agent doesn't have to re-derive it from
50 weeks of raw data every Monday.

## Your role

{role_prompt}

## Business context

{business_context}

## What to do

1. Read all data attached (the full historical window, typically 50 weeks).
2. Look for patterns: typical ranges, seasonality, repeated behaviors, attribution caveats.
3. Produce a baseline doc covering the sections below.

## Sections to produce

{sections}

## Output format

For each section, output **exactly** this shape:

```
[section_name]  (confidence=high|medium|low)
<content — 3-15 lines of dense, factual prose. Use numeric ranges where
applicable. Cite the data window the pattern is based on (e.g. "weeks
2025-W12 to 2026-W18"). Be specific, not generic.>
```

No preamble, no closing summary, no notes. Just the structured sections,
in the order listed, ready to paste into a spreadsheet.

## Data attached

{data_tabs}
"""


def build_one(spec: AgentSpec) -> str:
    role = (PROMPTS_DIR / spec.role_file).read_text().strip()
    context = (PROMPTS_DIR / "base_context.md").read_text().strip()
    sections_path = SECTIONS_DIR / f"{spec.name}.md"
    if not sections_path.exists():
        raise FileNotFoundError(f"Missing section asks for {spec.name}: {sections_path}")
    sections = sections_path.read_text().strip()
    data_tabs = "\n".join(f"- `{t}`" for t in spec.data_tabs)
    return TEMPLATE.format(
        agent=spec.name,
        friendly=spec.friendly,
        role_file=spec.role_file,
        role_prompt=role,
        business_context=context,
        sections=sections,
        data_tabs=data_tabs,
    )


def main() -> None:
    BASELINE_DIR.mkdir(exist_ok=True)
    for spec in AGENTS:
        out = build_one(spec)
        path = BASELINE_DIR / f"{spec.name}.md"
        path.write_text(out)
        print(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
