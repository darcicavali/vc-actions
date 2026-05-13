# Baselines — Operator Guide

## What a baseline is

A **baseline** is each agent's curated "mental model" of what's normal for the business. It answers questions like:

- What's the typical range for this metric?
- What patterns repeat every year (seasonality)?
- What attribution caveats apply?
- What hard rules has Darci set?
- What does the customer profile look like in aggregate?

It is **not** a copy of 50 weeks of raw data. It's the *wisdom extracted from* 50 weeks of data — typically 1-3 pages of text per agent.

The baseline lives in a Google Sheets tab named `BASELINE: <AgentName>` (one per agent). Each row is one named **section** with freeform `content`, a `last_updated` date, and a `confidence` rating.

## Why we have them

Without a baseline, every weekly run would need 50 weeks of raw data dumped into the prompt — slow, expensive, and the agent re-derives "what normal looks like" from scratch every Monday. With a baseline:

- The weekly prompt only needs **4 weeks** of recent data + the baseline doc
- Token cost drops ~85% per run
- Analysis quality goes **up** because the baseline is curated (and edited by you), not implicit pattern-matching

## How to build a baseline (Claude Max workflow)

You already pay for Claude Max ($200/mo flat). Using it for the baseline build means **zero API cost** for the one-time analysis. Each baseline takes ~5-10 minutes.

### Step 1 — Pick an agent

Start with `AdsAgent` (the most data-rich). Order doesn't otherwise matter; do them one at a time.

### Step 2 — Open `baseline_prompts/ads.md` and copy the prompt

Each file in `baseline_prompts/` is a self-contained prompt pack for one agent. It includes:

- The agent's role description
- The shared business context
- The output schema (which sections to produce)
- Instructions for what to attach

### Step 3 — Start a fresh Claude.ai conversation

- Go to claude.ai
- New conversation, model = Opus or Sonnet (your call)
- Paste the prompt from the baseline_prompts file

### Step 4 — Attach the relevant data

For each agent, the prompt pack lists which Google Sheets tabs to share. The simplest path:

- In Sheets, select the relevant tab → File → Download → CSV
- Drag the CSV into the Claude.ai conversation

Or, paste the data directly if it's short.

### Step 5 — Review the output

Claude will produce a structured baseline doc. **Read it critically:**

- Are the metric ranges believable for your business?
- Did it pick up the WhatsApp attribution caveat?
- Did it surface real seasonal patterns or invent them?
- Is anything missing that you'd want the weekly agent to know?

Edit as you go. Don't ship a baseline you don't agree with.

### Step 6 — Paste into the Sheets baseline tab

The output is structured as `[section_name] content` blocks. For each section:

1. Go to the `BASELINE: <AgentName>` tab in your spreadsheet
2. Add one row per section: `section` | `content` | `last_updated` (today) | `confidence` (high/medium/low)

That's it. Next weekly run, that agent will read its baseline.

### Step 7 — Repeat for the next agent

7 specialists + GoalsAgent = 8 baselines total. Plan ~1 hour total.

## How to refresh a baseline

**Default cadence:** monthly. The first week of every month, re-run the baseline pack for any agent whose business situation has shifted meaningfully (e.g., changed ad strategy, new SKU mix, seasonal shift).

**Trigger refresh sooner if:** the agent flags "this week breaks the baseline" three weeks in a row. That's a signal that your "normal" has actually moved.

**To refresh:** repeat steps 1-6, but tell Claude.ai *"Here's the current baseline (paste). Here's the latest 4 weeks of data (paste). Update the baseline where appropriate; preserve sections that are still accurate."*

## Editing baselines directly in Sheets

You don't need Claude.ai to edit a baseline. If you want to add a hard rule ("never recommend pausing the Maria collection"), just open the `BASELINE: AdsAgent` tab and add a row with `section=hard_rules`, `content=<your rule>`, today's date, `confidence=high`. The agent will see it on the next run.

## What if a baseline is empty?

The agents handle empty baselines gracefully — the prompt will say `(no baseline yet — first run, weekly data is the only signal)` and the agent will fall back to analyzing 4 weeks of raw data. You can deploy the system without any baselines and add them over time.
