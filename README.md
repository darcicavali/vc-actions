# vc-actions

Multi-agent strategic decision system for Vanessa Cavali Boutique.

7 specialist agents + 1 coordinator read weekly dashboard data and produce one unified action plan every Monday morning.

## What it does

Every Monday 8 AM CT, the system:

1. Reads weekly data from the Vanessa Cavali dashboard Google Sheet
2. Runs 7 specialist agents in parallel, each analyzing their domain using Claude API:
   - **AdsAgent** — paid media (Meta)
   - **CustomerAgent** — lifecycle, segments, retention
   - **ProductAgent** — buying, merchandising, returns
   - **ContentAgent** — Instagram organic
   - **FunnelAgent** — conversion, PDP, checkout
   - **FinancialAgent** — cash, margins, runway
   - **SEOAgent** — organic search, content gaps, local SEO
3. The **GoalsAgent (Coordinator)** reads all 7 memos and produces ONE unified action plan
4. Sends a digest email to Darci with sequenced weekly actions

## Architecture

```
agents/        - Python modules, one per agent, all inherit from BaseAgent
prompts/       - Markdown role prompts that define each agent's reasoning
scripts/       - Sheets, Claude API, Omnisend, Shopify clients + runner
tests/         - Pytest suite with fixture memos for coordinator testing
.github/workflows/ - Monday morning cron job
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env with real credentials
pytest
```

Required env vars:
- `ANTHROPIC_API_KEY`
- `GA4_CREDENTIALS_JSON`
- `OMNISEND_API_KEY`
- `GOOGLE_SHEET_ID`
- `SHOPIFY_ACCESS_TOKEN` (for SEOAgent product meta reads)

## Cost

~$0.50/week in Claude API calls. ~$25/year.

## Related repos

- `vc-dashboard` — the data pipeline. This repo reads from its Google Sheet.
- `vc-drops` — drop scheduling system (separate concern).
- `ig-gbp-sync` — cross-poster (provides GBP data SEOAgent reads).

## Spec

See `VC_ACTIONS_MULTIAGENT_FRAMEWORK_v4.md` in the repo root for the full build spec.
