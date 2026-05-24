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

**Code is built and tested.** 106 tests pass. The framework is *deployed* via GitHub Actions (`.github/workflows/weekly_run.yml`) — manual trigger + Monday 13:00 UTC cron.

---

## Current state (update this section every session)

**Last updated:** 2026-05-25

### Deployment status

- GitHub Actions workflow exists: `.github/workflows/weekly_run.yml`.
- Required secrets in GitHub: **ANTHROPIC_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, RESEND_API_KEY** — all in place.
- Required variables: **RESEND_TO** (Darci's email) — in place.
- Google Sheet shared with the service account email — done.
- **First dry-run failures all fixed in main:** 200k-token overflow (`535221c`), rate-limit pacing (`535221c`), Windows UTF-8 (`4ea6c46`, `005ae2e`).
- **Bootstrap_only run created all 10 new tabs** for $0 (`BASELINE: <Agent>` × 8, `Bot Actions`, `Bot Notes`).
- **First REAL production run (2026-05-22)** completed end-to-end after one fix: GoalsAgent's JSON was truncated at 2500-token output cap. Fixed in PR #8 by adding `preferred_max_tokens=8000` to GoalsAgent. All 7 specialists succeeded; coordinator now succeeds too on the re-run.
- **Resend integration** shipped in PR #9: weekly digest email goes via Resend (`onboarding@resend.dev`), reusing the API key from the `ig-gbp-sync` repo. Omnisend stays as fallback. Plain-text format optimized for phone reading.
- **`test_email` mode** shipped in PR #10: free-tier sample-email diagnostic, same pattern as `bootstrap_only` and `list_tabs`. Sends one realistic-looking sample digest, no agent runs, no Claude calls.
- **Resend wiring verified 2026-05-25** — test email landed in Darci's inbox after correcting `RESEND_TO` from secret to variable.

### Merged PRs (latest first)

| PR | Title | Status | Notes |
|---|---|---|---|
| #10 | `test_email` mode for free Resend wiring verification | ✅ Merged 2026-05-25 | Workflow input that sends a sample digest and exits. Used to confirm Resend wiring before Monday auto-run. |
| #9 | Send Monday digest via Resend | ✅ Merged 2026-05-25 | Reuses the API key from `ig-gbp-sync`. Omnisend stays as fallback. |
| #8 | Fix GoalsAgent JSON truncation | ✅ Merged 2026-05-22 | `preferred_max_tokens=8000` on GoalsAgent. Coordinator now succeeds on full action plan. |
| #7 | `list_tabs` flag for free read-only sheet inspection | OPEN | Adds workflow input to print every tab title. Darci provided tab list manually so not yet merged. |
| #6 | Fly.io deploy workflow for the Telegram chat bot | ✅ Merged 2026-05-19 | New `deploy_bot.yml` triggers `flyctl deploy --remote-only`. Not yet exercised — Fly setup pending. |
| #5 | `bootstrap_only` mode for free tab creation | ✅ Merged 2026-05-13 | Also moved `ensure_all_tabs()` out of the dry-run guard. |
| #4 | Land cost cuts + baseline layer + chat bot | ✅ Merged 2026-05-13 | Cost, baseline, chat bot all on main. |

### Baseline progress (Track A — Darci's manual workflow via Claude.ai Max)

| Agent | Status | Notes |
|---|---|---|
| AdsAgent | ✅ Filled 2026-05-19 | 7 sections — strong baseline (65+ age band waste $2.7k, freq>5 → CTR halving, current Apr-May creative drought, WhatsApp inflation caveat all captured) |
| CustomerAgent | ✅ Filled 2026-05-22 | 8 sections — 63.7% one-timers, top 5% = 51.9% revenue, "missing middle" 2-4 order segment, multiple confidence=low data gaps honestly flagged |
| ProductAgent | ✅ Filled 2026-05-22 | 8 sections — Remanessente/Fancy/Petite Poa/house-line identified as durable vendor priorities; Legging/Acessories/Blazer/Jackets flagged as margin traps; "Uncategorized" $36.9k revenue flagged as Shopify product-type tagging gap not buying issue; discount_thresholds left at confidence=low pending Darci's explicit markdown rule |
| ContentAgent | ✅ Filled 2026-05-22 | 8 sections — Carousels weakest format on this account (every one ≤280 reach), People > Product by 1.7x for reach, Profile Views (not Saves) predict Website Clicks (r=0.77) |
| FunnelAgent | ✅ Filled 2026-05-22 | 8 sections — View→ATC at 7.4% (vs 12% benchmark) is dominant leak, concentrated at PDP (44% engagement / 69s); Email's 0% GA4 conv is attribution leak not broken program; ~28% of weeks show IC→Purchase >100% from WhatsApp closes (not a bug) |
| FinancialAgent | ✅ Filled 2026-05-22 | 8 sections — CRITICAL: $360k goal mathematically out of reach (YTD $67.8k, need $36.5k/mo vs TTM avg $16.9k); margin compressing 49%→45% YTD; return rate breached (>15% for 6 of last 7 months); Feb26 discount breach (20.6%); ad spend + fixed costs data gaps flagged confidence=low |
| SEOAgent | 🟡 Next up | CSVs: Landing Pages (only existing tab). GBP/Search Console/Product Meta tabs don't exist yet — baseline will be lighter; expanded website-inspection capability deferred to Phase 2 |
| GoalsAgent (coordinator) | ⬜ | Built last — synthesizes patterns across all specialist baselines |

### Schema gaps (logged for later, not blocking)

Darci's sheet has 53 tabs. Most agent `data_tabs` declarations match cleanly. These don't:

- `Returns` — referenced by ProductAgent + FinancialAgent. Not in sheet. ProductAgent baseline noted "Returns: median 0% in both channels" from the customer tabs, so some data exists elsewhere.
- `COGS` — referenced by FinancialAgent. Not in sheet.
- `Margin Trends` — referenced by FinancialAgent. Not in sheet.
- `All Products` — referenced by ProductAgent. Sheet has `All Product by Type` and `All Product by Vendor` instead (split by dimension).
- `GBP Performance`, `Search Console Queries`, `Product Meta` — referenced by SEOAgent. None in sheet (external data sources not yet wired in).

Decision deferred until after baselines complete: either update agent `data_tabs` to match the actual sheet names, or extend the `vc-dashboard` upstream to produce these tabs.

### Track A — baselines (Darci's manual workflow via Claude.ai Max)

7 of 8 done (AdsAgent, CustomerAgent, ProductAgent, ContentAgent, FunnelAgent, FinancialAgent, SEOAgent). GoalsAgent baseline is intentionally deferred until 3-4 weekly runs accumulate — without run history there are no cross-agent patterns to synthesize.

### Track B — chat bot deployment

- Code merged in PR #4. Tested. 34 chat-layer tests passing.
- Fly.io deploy workflow merged in PR #6.
- **Now active (2026-05-25):** Darci ready to do Phase 1 (Telegram via @BotFather + @userinfobot). Phase 2 is Fly.io account + secrets + API token. Phase 3 is clicking the Deploy Bot workflow.

### Track C — maintenance reminders (planned, not built)

Darci asked for a way to be reminded of monthly baseline refreshes (and other recurring actions). Agreed approach: extend the existing Monday weekly email digest to include a "Maintenance" section that reads `last_updated` from every BASELINE tab and flags any older than 30 days OR never filled. Defer until ~Monday of June so the real cron pattern is established first.

### Next actions, in order

1. **Track B Phase 1 — Telegram setup** (in-progress). Darci creates bot via @BotFather, gets her user ID from @userinfobot.
2. **Track B Phase 2 — Fly.io account + secrets + API token.**
3. **Track B Phase 3 — trigger the Deploy Bot workflow.**
4. **Monday 2026-06-01 auto-run** — first scheduled cron, action plan + email delivered automatically.
5. **Build Track C (maintenance reminders)** after Monday run.
6. **GoalsAgent baseline** after 3-4 weekly runs accumulate (~end of June).
7. **Schema gap cleanup** (Returns / COGS / Margin Trends / All Products / GBP / Search Console / Product Meta) — non-blocking, defer until clearly needed.
8. **SEO Phase 2** (Search Console / GBP / website-fetch tools) — only if Darci asks for it after seeing the SEO baseline gaps in practice.

### Open requirement — two-way communication (NEW, not in v4/v5 spec)

Darci wants more than the weekly Monday email. The chat bot (Track B) is the answer; the code is merged but not yet deployed.

### Known blockers / unknowns

- Some agents reference tabs that don't exist in the sheet (see Schema gaps above). Not blocking — agents handle missing tabs gracefully with `data_quality: incomplete`.
- Omnisend automation listening for event `vc_weekly_plan` must be created manually by Darci before the digest email will actually send. Not blocking dry-runs.

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
