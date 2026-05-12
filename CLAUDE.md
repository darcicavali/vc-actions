# CLAUDE.md — Session memory for vc-actions

**Read this first, every session, before doing anything else.**

This file plus the latest entries in `BUILD_JOURNAL.md` (especially the `## Ops —` entries at the bottom) are the only way a new session knows where we are. Always read both before responding to Darci.

---

## Who I'm working with

**Darci** owns Vanessa Cavali Boutique. She is the product owner, not a programmer. She wants me to do the engineering and translate it into clear, short instructions for her.

### Communication rules — non-negotiable

- **No terminal commands** unless strictly, unavoidably necessary. Default to GUI / web / one-click paths (GitHub web UI, Google Sheets, Notepad, etc.).
- **Short chat answers.** Darci reads slowly and is time-constrained. Long explanations belong in files she can re-read on her own time, not in chat.
- **Very clear instructions.** Numbered steps. One action per step. No jargon without a plain-language gloss.
- **Ask before risky/irreversible steps** (push, merge, delete, send email, share data externally).
- **When something fails, she pastes the error and I fix it.** She does not debug.
- **Always put action items needed from Darci at the BOTTOM of the chat reply**, clearly labeled (e.g. "## What I need from you" or "## Action needed"). This is so she can scroll straight to what she has to do without re-reading the whole reply. Stated by Darci in the prior session, must be honored permanently.

### What Darci is NOT going to do

- Open a terminal
- Install Python / pip / packages locally
- Edit code by hand
- Run scripts on her own machine

---

## What we're building

`vc-actions` — 7 specialist Claude agents + 1 coordinator. Every Monday 8 AM CT, they read weekly data from the `vc-dashboard` Google Sheet and produce one unified action plan, emailed to Darci via Omnisend.

**Specs (source of truth, do not modify without Darci):**
- `VC_ACTIONS_MULTIAGENT_FRAMEWORK_v4.md` — architecture
- `VC_ACTIONS_MEMORY_AND_JOURNAL_v5.md` — memory layers + journaling
- `BUILD_JOURNAL.md` — what happened, session by session

**Code is built and tested.** 62 tests pass. The framework is *deployed* via GitHub Actions (`.github/workflows/weekly_run.yml`) — manual trigger + Monday 13:00 UTC cron.

---

## Current state (update this section every session)

**Last updated:** 2026-05-12

### Deployment status

- GitHub Actions workflow exists: `.github/workflows/weekly_run.yml`.
- Required secrets in GitHub: **ANTHROPIC_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON** — added in a prior session.
- Google Sheet shared with the service account email — done in a prior session.
- **First dry-run was attempted and surfaced 3 real failures, all now fixed in main:**
  1. Per-tab row dump pushed prompts over Claude's 200k token limit. Fixed: `BaseAgent` caps each tab at 50 most-recent rows (commit `535221c`).
  2. Specialists hit Anthropic's 30k input-tokens/minute rate limit. Fixed: runner sleeps `VC_ACTIONS_INTER_AGENT_DELAY_SECONDS` (default 60s) between specialists (commit `535221c`).
  3. Windows `cp1252` locale broke prompt-file reads (em dashes). Fixed: UTF-8 pinned on every prompt/journal read (commits `4ea6c46`, `005ae2e`).

### Unmerged work sitting on `origin/claude/build-multiagent-system-Q4Z6T`

Three commits pushed but **never merged into `main`**. Discovered 2026-05-12 by reading the prior session transcript Darci shared. These are real, tested code (104 tests pass on that branch) that we need to land:

1. **`55fbc73` — Cost cuts (PR 3):** prompt caching, Haiku 4.5 routing for Content + SEO, default 50→12 rows/tab. Drops per-run cost ~85% (~$0.80 → ~$0.10–0.15).
2. **`bb61af9` — Baseline layer (PR 4):** new `BASELINE: <Agent>` tabs (one per agent) carry curated long-run wisdom. `baseline_prompts/` directory holds paste-into-Claude.ai prompt packs; `BASELINES.md` is the operator guide for refreshing them via Darci's Claude Max subscription (no API cost). Default rows/tab drops further (12→4) because the baseline replaces raw history.
3. **`87c8270` — Chat bot (PR 5):** `chat/` package — Streamlit web UI (`chat/web_app.py`) + Telegram long-polling bot (`chat/telegram_app.py`) over one shared `brain.py`. SQLite conversation memory. `Bot Actions` audit tab + `Bot Notes` forward-channel tab. Guardrail framework wired for future destructive tools (none today; only append-only writes ship). Dockerfile + `fly.toml` stubs for Fly.io deploy when Darci's ready.

### Next actions, in order

1. **Land the unmerged branch into `main`** — one PR with all three commits is simplest. Darci needs to authorize me to open it.
2. **Re-trigger the dry-run** from GitHub Actions web UI once #1 is merged. Confirms the rate-limit / token-cap / UTF-8 fixes hold AND that the cost optimizations work in production.
3. **Stand up the chat bot locally** — Streamlit first (laptop), then Telegram (phone). Requires Darci to create a Telegram bot via `@BotFather` and grab her user ID via `@userinfobot` (web/app, no terminal).
4. **Scope the baseline-prompt workflow** — Darci pastes each agent's `baseline_prompts/*.md` into a Claude.ai conversation, attaches relevant CSVs, gets back a populated baseline she pastes into the `BASELINE: <Agent>` tab. Repeats monthly.

### Open requirement — two-way communication (NEW, not in v4/v5 spec)

Darci wants more than the weekly Monday email. She wants to be able to **ask questions and give instructions to the agents** between weekly runs. Last session she asked about:

1. **Telegram bot** — chat with the agents from her phone
2. **Desktop chat** — same thing but on her computer

This is not yet designed or built. The spec docs predate this requirement. Treat it as an active open requirement to scope next.

### Known blockers / unknowns

- Tab names in `vc-dashboard` for non-Meta specialists are best-guess from the spec. First dry-run will surface any mismatches as `WorksheetNotFound` in the data block (will not crash the run, just degrade data quality).
- Omnisend automation listening for event `vc_weekly_plan` must be created manually by Darci before the digest email will actually send. Not blocking dry-run.

---

## How sessions work going forward

### Start of every session (me)

1. Read this file (`CLAUDE.md`) — auto-loaded by Claude Code.
2. Read the last 1–2 ops entries at the bottom of `BUILD_JOURNAL.md`.
3. Tell Darci in one sentence where we are and what's next. Do **not** ask her to re-explain.

### End of every session (me)

1. Append a new `## Ops — YYYY-MM-DD — <short title>` entry to `BUILD_JOURNAL.md` with:
   - What was attempted
   - What worked
   - What failed / had to retry
   - Decisions made
   - Open questions
   - Next step
2. Update the **Current state** section above (overwrite — it's a snapshot, not a log).
3. Commit + push so the next session reads the update.

### If a session breaks mid-task

The most recent commit on the working branch is the recovery point. If nothing was committed yet, the journal entry from the previous session is the recovery point. Always pick up there, do not start over.

---

## Architecture quick reference

```
agents/        Python modules, one per agent, all inherit from BaseAgent
prompts/       Markdown role prompts that define each agent's reasoning
scripts/       Sheets, Claude, Omnisend, Shopify clients + runner
tests/         Pytest suite (57 tests, ~0.3s)
.github/workflows/weekly_run.yml   Monday 13:00 UTC cron + manual trigger
```

### Where things run

- **Production:** GitHub Actions (cloud, free for this scale). Reads secrets from GitHub Secrets, not from any `.env` file.
- **Local `.env`:** not needed for production. Only used if a developer wants to run tests locally. Darci will not run this locally.
- **Triggering manually:** https://github.com/darcicavali/vc-actions/actions/workflows/weekly_run.yml → "Run workflow" button.

### Secrets live in two places — do not confuse them

- **GitHub repository secrets** (production): https://github.com/darcicavali/vc-actions/settings/secrets/actions
- **Local `.env`** (developer convenience only, never deployed): in repo root, gitignored.

---

## My standing instructions

- Edit existing files; do not create new docs unless Darci asks.
- Do not create PRs unless Darci asks.
- Push commits to the working branch the harness assigns (currently `claude/resume-previous-session-3LuS4`).
- When unsure, ask one focused question with concrete options, not an open-ended "what do you want?"
