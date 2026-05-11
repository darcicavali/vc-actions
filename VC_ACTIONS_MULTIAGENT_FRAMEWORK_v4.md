# vc-actions — Multi-Agent Framework (v4 Spec)

**Owner:** Darci (Vanessa Cavali Boutique)
**Scope:** Multi-agent system where 7 specialist agents + 1 coordinator produce a unified weekly action plan
**Status:** Greenfield repo. Replaces all prior phase 2 specs.

---

## The shift in approach

Previous specs (v1-v3) were rule-based: "if ROAS < X, pause." That's rigid. A real expert reasons contextually: "ROAS is low but it's December auction pressure, hold steady."

This v4 spec uses **Claude as the reasoning engine** inside each agent. Each agent is a domain specialist that:

1. Pulls relevant data from the dashboard sheet
2. Sends data + business context + role prompt to Claude API
3. Receives structured analysis back
4. Writes a memo to a shared sheet tab

A **Coordinator agent** then reads all memos and produces a single unified weekly action plan, surfacing cross-domain synergies and resolving conflicts.

---

## The 8 agents

```
┌────────────────────────────────────────────────────────┐
│              GoalsAgent (Coordinator)                  │
│   reads all 7 memos → 1 unified weekly action plan     │
└────────────────────────────┬───────────────────────────┘
                             │
   ┌────────┬────────┬───────┼───────┬────────┬────────┐
   │        │        │       │       │        │        │
 Ads   Customer Product Content Funnel  SEO   Financial
```

### 1. AdsAgent — Paid Media Strategist
**Role:** Senior digital marketing strategist specializing in DTC fashion paid social.
**Data:** Meta Ads Summary, by Campaign, by Ad Set, by Ad, Demographics
**Focus:** Cold + warm-non-customer campaigns. Warm-customer monitored only (50% WhatsApp inflation).
**Key reasoning:** funnel-stage diagnosis (CPM/CTR/ATC%/IC% patterns), audience saturation, creative fatigue, attribution caveats.

### 2. CustomerAgent — CRM/Lifecycle Specialist
**Role:** Retention and lifecycle expert.
**Data:** All Customers, Seg Special (VIP/At Risk), Seg Recency, Retention Summary/Detail, Customer Rankings (Online/POS)
**Focus:** segment health, retention trends, win-back effectiveness, VIP pipeline.
**Key reasoning:** are we keeping good customers? Is the VIP pipeline growing? Where are we losing people in the lifecycle?

### 3. ProductAgent — Merchandising & Buying
**Role:** Boutique buyer and merchandising strategist.
**Data:** Product by Type, Product by Vendor, All Products, returns data
**Focus:** what to reorder, what to drop, what's killing margin, return rates by product/type.
**Key reasoning:** inventory→revenue alignment, margin health by SKU class, dead stock, what's hot.

### 4. ContentAgent — Organic Social Strategist
**Role:** IG/organic content strategist for fashion DTC.
**Data:** IG Summary, IG Posts, IG Content Types
**Focus:** what content drives saves, shares, website clicks. Reel vs static vs carousel. Content-to-revenue link.
**Key reasoning:** which content types correlate with conversion-quality traffic, when to post, what themes resonate.

### 5. FunnelAgent — Conversion/CRO Specialist
**Role:** E-commerce conversion expert.
**Data:** Weekly Summary funnel (Sessions→VI→ATC→IC→Purchase), Landing Pages, Device Breakdown, Funnel by Source
**Focus:** where the funnel leaks, by source, by device, by landing page.
**Key reasoning:** is the View→ATC drop product page or trust? Is checkout dropping people? Device-specific problems?

### 6. FinancialAgent — Cash Flow & Margins
**Role:** Boutique CFO. Watches the heartbeat.
**Data:** Financial Summary, Monthly Financial, returns, COGS, margin trends
**Focus:** margin trends, inventory turnover, cash flow health, discounting creep, runway.
**Key reasoning:** can we afford this action? Are margins sustainable? Where's cash tied up?

### 7. SEOAgent — Organic Search Specialist
**Role:** SEO/content strategist for local + DTC fashion.
**Data:** Landing Pages (GA4), GBP performance from ig-gbp-sync, Shopify product meta (via API call), optionally Google Search Console queries
**Focus:** product page SEO, content gap opportunities, local search visibility, blog topic recommendations.
**Key reasoning:** what are people searching for that we should rank for? Are our product pages optimized? Is the Geneva/Chicago local presence strong?

### 8. GoalsAgent (Coordinator) — Strategic Synthesis
**Role:** Senior strategist + COO. Reads all 7 specialist memos. Holds yearly goal ($360k) and runway in mind.
**Data:** all agent memos + Goal Tracker tab (yearly target, YTD, pace)
**Focus:** ONE coordinated weekly action plan, not 7 separate recommendations.
**Key reasoning:** find cross-agent themes, resolve conflicts, rank by feasibility×impact, sequence actions.

---

## Architecture

### Repo: `vc-actions` (new)

```
vc-actions/
├── .github/workflows/
│   └── weekly_run.yml          # Monday 8am CT
├── agents/
│   ├── __init__.py
│   ├── base.py                 # BaseAgent class
│   ├── ads_agent.py
│   ├── customer_agent.py
│   ├── product_agent.py
│   ├── content_agent.py
│   ├── funnel_agent.py
│   ├── financial_agent.py
│   ├── seo_agent.py
│   └── goals_agent.py          # Coordinator
├── prompts/
│   ├── base_context.md         # business context all agents share
│   ├── ads.md                  # AdsAgent role prompt
│   ├── customer.md
│   ├── product.md
│   ├── content.md
│   ├── funnel.md
│   ├── financial.md
│   ├── seo.md
│   └── coordinator.md
├── scripts/
│   ├── __init__.py
│   ├── config.py
│   ├── claude_client.py        # Anthropic API wrapper
│   ├── sheets_client.py        # adapt from vc-drops
│   ├── omnisend_client.py      # for digest email
│   ├── shopify_client.py       # for SEO product meta reads
│   ├── memo_store.py           # read/write Agent Memos tab
│   └── runner.py               # orchestrates weekly run
├── tests/
│   ├── conftest.py
│   ├── test_base_agent.py
│   ├── test_memo_store.py
│   ├── test_coordinator.py
│   └── fixtures/
│       ├── memos_healthy_week.json
│       └── memos_problem_week.json
├── requirements.txt
├── .env.example
└── README.md
```

### `agents/base.py` — Foundation

```python
from dataclasses import dataclass, field
from typing import Any
import anthropic

@dataclass
class Recommendation:
    priority: int                # 1 (highest) to 5
    action: str                  # e.g. "Scale Prospect ASC +$10/day"
    why: str                     # one sentence reasoning
    impact_dollars_per_week: float
    confidence: str              # high / medium / low
    effort: str                  # low / medium / high
    depends_on: list[str] = field(default_factory=list)

@dataclass
class AgentMemo:
    agent: str                   # e.g. "AdsAgent"
    generated_at: str
    summary: str                 # 1-2 sentence top-line
    diagnosis: str               # 2-4 sentences on what's happening
    recommendations: list[Recommendation]
    watch_list: list[str]        # things to monitor next week
    data_quality: str            # high / medium / low
    raw_response: str            # full Claude response for debugging

class BaseAgent:
    """Every specialist agent inherits from this."""

    name: str = ""               # override in subclass
    role_prompt_file: str = ""   # path to prompts/{name}.md

    def __init__(self, claude_client, sheets_client, config):
        self.claude = claude_client
        self.sheets = sheets_client
        self.config = config

    def gather_data(self) -> dict:
        """Override: pull relevant sheet tabs + format for prompt."""
        raise NotImplementedError

    def get_business_context(self) -> str:
        with open("prompts/base_context.md") as f:
            return f.read()

    def get_role_prompt(self) -> str:
        with open(self.role_prompt_file) as f:
            return f.read()

    def run(self) -> AgentMemo:
        data = self.gather_data()
        context = self.get_business_context()
        role = self.get_role_prompt()

        prompt = f"""{role}

BUSINESS CONTEXT:
{context}

THIS WEEK'S DATA:
{data}

Produce a structured analysis in JSON matching this schema:
{{
  "summary": "...",
  "diagnosis": "...",
  "recommendations": [
    {{"priority": 1, "action": "...", "why": "...",
      "impact_dollars_per_week": 500, "confidence": "high",
      "effort": "low", "depends_on": []}}
  ],
  "watch_list": ["..."],
  "data_quality": "high"
}}

Return ONLY the JSON, no preamble.
"""

        response = self.claude.complete(prompt)
        memo = self._parse_response(response)
        self._write_memo(memo)
        return memo

    def _parse_response(self, response: str) -> AgentMemo: ...
    def _write_memo(self, memo: AgentMemo) -> None: ...
```

### `prompts/base_context.md` — Shared business context

```markdown
# Vanessa Cavali Boutique — Business Context

## What we are
A premium Brazilian women's fashion boutique in Geneva, IL. Small inventory,
fast SKU turnover, rarely restocked. AOV $100-150. Brand emphasizes
craftsmanship and one-of-a-kind pieces.

## Where we are
- Revenue: ~$25k/month
- YTD: $67k by end of April
- Yearly target: $360k
- Gap to close: $293k over May-Dec ($36.6k/month average needed)

## Channels
- Shopify online store (~50% of revenue)
- WhatsApp/IG DMs/Live shopping (~50%, attributed in dashboard as
  draft orders + RT-customer ad clicks)
- Geneva IL physical store + occasional pop-ups (POS)

## Constraints
- Capital-limited: cannot fund big bets
- Solo operator on marketing/finance/tech (Darci); partner handles ops
- Inventory is boutique-scale: small SKU count, rarely restocked

## What we value
- Brand integrity (no deep discounting)
- Customer relationships (Vanessa personally engages on WhatsApp)
- Sustainable pace over hyper-growth

## Active paid campaigns
- Prospect ASC (cold) — ~53% of spend
- RT - non customer (warm-non-customer) — ~36%
- RT-customer (warm-customer, WhatsApp-inflated) — ~11%

## Attribution caveats
- ~50% of revenue from existing customers closes on WhatsApp;
  Meta still attributes to RT-customer campaign
- Treat RT-customer ROAS as suspect (effective ~50% of reported)
```

### `prompts/ads.md` — Example role prompt

```markdown
# Role: Senior Digital Marketing Strategist (Paid Social)

You are a senior digital marketing strategist with 10+ years of experience
running paid social for DTC fashion brands at boutique scale ($1-5k/month
ad spend).

Your specialty is reading the funnel: not just ROAS, but CPM, CTR, CPC,
frequency, ATC rate, IC rate, and purchase rate together. You diagnose
WHERE in the funnel a problem is and WHY.

You understand boutique constraints: small budgets need small budget
moves ($5-10/day), not 20% blasts. You know when to refresh the product
feed vs. when to develop new creative concepts.

You're skeptical of attribution. You flag WhatsApp inflation on
warm-customer campaigns. You distinguish auction pressure (CPM rising
across the board) from campaign-specific problems.

You produce concrete actions Darci can execute in 5 minutes, not
abstract strategy.

Focus ANALYTICAL DEPTH on cold + warm-non-customer campaigns. For
warm-customer campaigns, do a light health check only.

Recommendation philosophy:
- Lead with what's bleeding cash (pause/refresh)
- Then what could scale (small budget increases)
- Then what to investigate (anomalies)
- Tag every recommendation with $/week impact estimate
```

### `agents/goals_agent.py` — Coordinator

```python
class GoalsAgent(BaseAgent):
    name = "GoalsAgent"
    role_prompt_file = "prompts/coordinator.md"

    def gather_data(self) -> dict:
        memos = self.memo_store.read_all_memos_this_week()
        goal_tracker = self.sheets.read_tab("Goal Tracker")
        return {
            "yearly_target": 360_000,
            "ytd_revenue": self._compute_ytd(),
            "weeks_remaining": self._weeks_remaining(),
            "pace_per_week_needed": self._pace_needed(),
            "all_memos": memos,
        }

    def run(self) -> AgentMemo:
        # Same as BaseAgent.run but with coordinator-specific prompt
        # Output schema includes "themes", "conflicts_resolved",
        # "one_thing_this_week", "sequenced_actions"
        ...
```

### `prompts/coordinator.md`

```markdown
# Role: Strategic Coordinator / Fractional COO

You are reading 7 specialist memos and producing ONE coordinated weekly
action plan.

Your job is NOT to summarize the memos. Your job is to:

1. Identify CROSS-AGENT THEMES (e.g. "dresses are mentioned by Product,
   Content, AND Funnel agents — likely the highest-leverage focus")
2. Resolve CONFLICTS (e.g. if AdsAgent says scale and FinancialAgent
   says preserve cash, weigh both)
3. Rank by IMPACT × FEASIBILITY (cheap easy actions before expensive
   hard ones)
4. Sequence actions across the week
5. Identify the ONE THING — if Darci does nothing else this week,
   what matters most?
6. Tie it back to the $360k yearly goal: are we on pace? What's the
   gap and what closes it?

Output format:
- summary: 2 sentences on the week
- one_thing_this_week: the single highest-leverage move
- themes: 2-4 cross-agent themes
- sequenced_actions: 5-8 actions in order, each tagged with
  agent_source, day_of_week, effort, impact
- pace_status: on/behind/ahead, with gap-closing math
- conflicts_resolved: how you weighted competing recommendations
- watch_list: things to revisit next week
```

### `scripts/runner.py`

```python
from agents import (
    AdsAgent, CustomerAgent, ProductAgent, ContentAgent,
    FunnelAgent, FinancialAgent, SEOAgent, GoalsAgent
)

def run_weekly():
    config = get_config()
    claude = ClaudeClient(api_key=config.anthropic_api_key)
    sheets = SheetsClient()
    memo_store = MemoStore(sheets)

    specialists = [
        AdsAgent(claude, sheets, config),
        CustomerAgent(claude, sheets, config),
        ProductAgent(claude, sheets, config),
        ContentAgent(claude, sheets, config),
        FunnelAgent(claude, sheets, config),
        FinancialAgent(claude, sheets, config),
        SEOAgent(claude, sheets, config),
    ]

    # Phase 1: run specialists (independent, parallelizable)
    for agent in specialists:
        try:
            print(f"[{agent.name}] running...")
            memo = agent.run()
            print(f"[{agent.name}] {len(memo.recommendations)} recs")
        except Exception as e:
            print(f"[{agent.name}] failed: {e}")
            # continue — coordinator works with whatever succeeded

    # Phase 2: coordinator synthesizes
    coordinator = GoalsAgent(claude, sheets, config)
    plan = coordinator.run()

    # Phase 3: email digest
    send_weekly_plan_email(plan, config)

    print(f"[Weekly] Complete. {plan.summary}")

if __name__ == "__main__":
    run_weekly()
```

---

## Sheet tabs (new)

### `Agent Memos` — append-only log

Headers:
```
generated_at, agent, summary, diagnosis, recommendations_json,
watch_list_json, data_quality, raw_response
```

Append one row per agent per weekly run. Coordinator reads "last 7 days" worth.

### `Action Plan` — overwritten weekly

Headers (the coordinator's output, parsed):
```
generated_at, one_thing_this_week, pace_status, gap_to_close,
sequenced_actions_json, themes_json, conflicts_resolved, watch_list_json
```

### `Goal Tracker` — manual, weekly

Headers:
```
week_start, week_revenue, ytd_revenue, target_pace, gap, notes
```

Auto-populated from Weekly Summary tab + manual notes column for Darci.

---

## Weekly digest email

Sent Monday 8 AM CT. Single email from coordinator, not 7 emails.

```
WEEK ENDING MAY 9 — UNIFIED ACTION PLAN

📊 Goal pace: $67.2k YTD / $360k target
   Need $36.6k/mo through Dec. Last month: $25k (-32% behind pace).

🎯 ONE THING THIS WEEK:
   Push prospecting + restock signature dresses

   Why? Four agents converged:
   • CustomerAgent: VIP segment shrunk 12% — acquisition weak
   • AdsAgent: Prospect ASC healthy, room to scale
   • ProductAgent: Dresses 60% revenue, 25% inventory — reorder
   • ContentAgent: Dress carousels get 3x saves

🔧 SEQUENCED ACTIONS:

   MONDAY:
   1. Increase Prospect ASC budget +$10/day [AdsAgent, $40/wk impact]
   2. Submit reorder for top 3 dresses ($300) [ProductAgent, $1.5k/mo impact]

   WEDNESDAY:
   3. Refresh RT-non-customer creative — freq at 3.54 [AdsAgent]
   4. Post dress carousel to IG [ContentAgent]

   THURSDAY:
   5. Add meta description to 5 sold-out dress PDPs [SEOAgent]

⚠️ WATCH NEXT WEEK:
   • RT-non-customer ROAS if creative refresh doesn't hit
   • Cash position after dress reorder
   • Account ATC rate trend (down 22% w/w this week)

🚨 CONFLICTS RESOLVED:
   AdsAgent wanted +$15/day on Prospect; FinancialAgent flagged
   cash for dress reorder. Coordinator: split — $10/day to ads,
   $300 to inventory. Both fit weekly budget.

Full agent memos: <sheet URL>
```

---

## Manual setup Darci must do (one time)

1. **Anthropic API key** in repo secret `ANTHROPIC_API_KEY`
2. **One Omnisend automation** triggered by event `vc_weekly_plan`
3. **GitHub repo secrets:** `GA4_CREDENTIALS_JSON`, `SHOPIFY_ACCESS_TOKEN`, `OMNISEND_API_KEY`, `GOOGLE_SHEET_ID`, `ANTHROPIC_API_KEY`
4. **Verify SEOAgent data sources:** is Google Search Console connected to GA4? If yes, query data unlocks. If no, SEOAgent works with GA4 landing page data only.
5. **Edit `prompts/base_context.md`** to update business context as it changes (e.g., new revenue targets, channel mix shifts)

---

## Cost estimate

Per weekly run, with Claude Sonnet 4.5:
- 7 specialists × ~10k input tokens × ~2k output tokens = ~$0.40
- 1 coordinator × ~20k input tokens × ~3k output tokens = ~$0.15
- **Total: ~$0.55/week = ~$30/year**

Trivial. Could afford to run twice weekly if useful.

---

## Build order

| Phase | What | Hours |
|---|---|---|
| 1 | Repo scaffold + `claude_client.py` + `sheets_client.py` + `memo_store.py` + tests | 2 |
| 2 | `agents/base.py` + `prompts/base_context.md` + test agent harness | 1.5 |
| 3 | AdsAgent + `prompts/ads.md` + integration test | 1.5 |
| 4 | CustomerAgent + ProductAgent (parallel work, similar pattern) | 2 |
| 5 | ContentAgent + FunnelAgent | 2 |
| 6 | FinancialAgent + SEOAgent | 2 |
| 7 | GoalsAgent (Coordinator) + `prompts/coordinator.md` | 2 |
| 8 | `runner.py` + digest email + workflow | 1 |
| 9 | End-to-end live test + tune prompts based on real output | 2 |

**Total: ~16 focused hours (2 days of solid work)**

---

## Acceptance criteria

1. Run with `test_mode=true` → all 7 specialist memos written to `Agent Memos` tab
2. Coordinator memo written to `Action Plan` tab with cross-agent themes identifiable
3. Email digest received, structured as shown above
4. Each agent's recommendations are concrete (specific budget, specific products, etc.) not vague
5. Coordinator identifies at least 1 cross-agent theme when multiple agents reference same topic
6. Costs ~$0.50-1.00 per weekly run (Claude API)
7. `pytest` all green

---

## Out of scope

- Auto-acting on recommendations (still manual execution)
- Real-time analysis (weekly only)
- Agent-to-agent direct communication (star pattern, no mesh)
- Web search by agents (data is in sheet, no external research)
- ML/training (zero-shot Claude with good prompts)
- A/B testing the prompts (do this manually based on output quality)

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Claude produces hallucinated recommendations | Each agent's gather_data returns ONLY real numbers; prompt instructs "use only provided data" |
| Agents conflict and coordinator can't resolve | Coordinator prompt explicitly weighs financial cost vs revenue impact |
| One agent fails, blocks weekly run | Try/except per agent; coordinator works with whatever succeeded |
| Memos drift from useful into generic | Manually review weekly outputs, refine role prompts |
| API cost spirals | Cap input tokens per agent at 30k; cap weekly cost at $5 alert |

End of v4 spec.
