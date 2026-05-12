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

**Code is built and tested.** 57 tests pass. The framework is *deployed* via GitHub Actions (`.github/workflows/weekly_run.yml`) — manual trigger + Monday 13:00 UTC cron.

---

## Current state (update this section every session)

**Last updated:** 2026-05-12

### Deployment status

- GitHub Actions workflow exists: `.github/workflows/weekly_run.yml`
- Required secrets in GitHub: **ANTHROPIC_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON** — added (per Darci, completed in a prior session)
- Google Sheet shared with the service account email — done (per Darci, prior session)
- **Next action:** trigger first dry-run from the GitHub Actions web UI. Not yet done.

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
