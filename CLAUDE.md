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

**Last updated:** 2026-05-25 (eve)

### Deployment status

- GitHub Actions workflow `weekly_run.yml` exists. Monday 13:00 UTC cron + manual dispatch.
- GitHub Actions workflow `deploy_bot.yml` exists. Manual dispatch + auto on `chat/**` push.
- Required GitHub secrets: **ANTHROPIC_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, RESEND_API_KEY, FLY_API_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID** — all in place.
- Required GitHub variables: **RESEND_TO** — in place.
- Google Sheet shared with the service account email — done.
- **Weekly run path verified end-to-end** (2026-05-22). All 7 specialists succeeded; GoalsAgent failed once on token truncation; fixed in PR #8. Re-run after fix not yet exercised — first auto-run is Monday 2026-06-01.
- **Resend email path verified** via `test_email` mode (PR #10). Sample digest landed in Darci's inbox 2026-05-25.
- **Chat bot is LIVE on Fly.io** as of 2026-05-25 (eve). Telegram replies to Darci, ignores everyone else. Two bugs surfaced during deploy and were fixed: `load_config`→`get_config` import typo (PR #12), and the dual-machine issue (Fly default created 2 machines; Telegram only allows 1 long-poller per bot token; Darci deleted the second machine via Fly dashboard).

### Merged PRs (latest first)

| PR | Title | Status | Notes |
|---|---|---|---|
| #12 | Fix chat module imports — get_config not load_config | ✅ Merged 2026-05-25 | The bot crashed on import; tests don't cover transports yet. |
| #11 | Self-contained deploy_bot workflow | ✅ Merged 2026-05-25 | Creates Fly app + stages secrets + deploys, all from one click. |
| #10 | test_email mode for free Resend wiring verification | ✅ Merged 2026-05-25 | Saved Darci from waiting until Monday to discover wiring bugs. |
| #9 | Send Monday digest via Resend | ✅ Merged 2026-05-25 | Reuses ig-gbp-sync API key. Omnisend stays as fallback. |
| #8 | Fix GoalsAgent JSON truncation | ✅ Merged 2026-05-22 | `preferred_max_tokens=8000` on coordinator. |
| #7 | list_tabs flag for free sheet inspection | OPEN | Diagnostic; not blocking. |
| #6 | Fly.io deploy workflow stub | ✅ Merged 2026-05-19 | Superseded by PR #11. |
| #5 | bootstrap_only mode for free tab creation | ✅ Merged 2026-05-13 | Also always-on ensure_all_tabs. |
| #4 | Cost cuts + baseline layer + chat bot | ✅ Merged 2026-05-13 | Foundation merge. |

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

- ✅ DEPLOYED and live as of 2026-05-25 (eve). Bot responds to Darci in Telegram.
- Hosted on Fly.io, single machine (`shared-cpu-1x`, 256MB), region `ord`. App name: `vc-actions-bot`.
- Bot reads: every sheet tab, baselines, recent memos, action plan, outcomes. Writes (append-only): `Bot Actions` audit log, `Agent Knowledge` lessons, `Bot Notes` forward-channel notes.
- Auth: only Darci's Telegram user ID gets responses. Everyone else silently ignored.
- Next defensive improvement: lock `count=1` in deploy workflow so Fly never creates a second machine again (Telegram bot tokens only allow one long-poller).

### Track C — maintenance reminders (planned, not built)

Darci asked for a way to be reminded of monthly baseline refreshes (and other recurring actions). Agreed approach: extend the existing Monday weekly email digest to include a "Maintenance" section that reads `last_updated` from every BASELINE tab and flags any older than 30 days OR never filled. Defer until ~Monday of June so the real cron pattern is established first.

### Next actions, in order

1. **Set spending limit on Anthropic API key** (https://console.anthropic.com/settings/limits). No cap currently — risk of runaway cost if chat bot is misused or there's a runaway loop. Recommended: $50/month soft limit.
2. **Set Fly billing alert** (https://fly.io/dashboard/personal/billing). Recommended: $10/month alert. Practical bot cost is ~$0–3/month.
3. **Lock Fly machine count = 1** in the deploy workflow (defensive — prevents the dual-machine issue from recurring). Small follow-up PR.
4. **Smoke test for chat transports** — add `import chat.telegram_app` / `import chat.web_app` test so import errors fail in CI, not on Fly. Small follow-up PR.
5. **Monday 2026-06-01 auto-run** — first scheduled cron. Action plan written to sheet, email delivered via Resend. **No action required from Darci.**
6. **Build Track C (maintenance reminders)** after Monday run.
7. **GoalsAgent baseline** after 3-4 weekly runs accumulate (~end of June).
8. **Schema gap cleanup** (Returns / COGS / Margin Trends / All Products / GBP / Search Console / Product Meta) — non-blocking, defer.
9. **SEO Phase 2** (Search Console / GBP / website-fetch tools) — only if Darci asks after seeing the SEO baseline gaps in practice.

### Cost model (monthly)

| Component | Cost | Notes |
|---|---|---|
| Weekly cron (4×/mo) | $0.40–1.20 | $0.10–0.30/run × 4. Lower once baselines fully compress prompts. |
| Fly.io hosting (always-on bot) | $0–3 | $5/mo free credit usually covers; cap at $10/mo alert. |
| Chat bot Anthropic usage | $1–30 | Variable. $0.01–0.02/message with caching. 10 msg/day → ~$3–6/mo. |
| Resend email | $0 | 3K/mo free tier; we send ~5/mo. |
| **Total** | **~$5–35/mo** | Plus Claude.ai Max ($200/mo) for monthly baseline refreshes — pre-existing. |

### Safety measures (review 2026-05-25)

**Protections in place:**
- Telegram bot ignores everyone except Darci's user ID (silent allow-list).
- Chat bot write tools are append-only (`add_lesson`, `note_for_next_run`). No tool can delete or overwrite existing data.
- `chat/guardrails.py` framework — any future destructive tool will require explicit confirmation before execution.
- All API keys / service account JSON stored as GitHub Secrets + Fly Secrets (encrypted at rest, masked in logs).
- Single Fly machine, fixed size — no auto-scaling, no runaway spend risk on hosting side.
- Service account permissions limited to one Google Sheet (vc-dashboard), not the broader Google account.
- Resend free tier rate-limited (100/day, 3K/mo) — caps email volume even on misuse.

**Open security follow-ups:**
- No spending cap on Anthropic API key — recommend setting in Anthropic console.
- No 2FA enforcement check on GitHub / Fly / Anthropic — Darci should ensure 2FA is on for all three.
- Conversation history stored in SQLite on Fly machine — if Fly machine compromised, conversation data exposed. Acceptable for this scale.
- Telegram bot token in plain-readable GitHub secret — anyone with repo write access could read it via a malicious workflow. Mitigated by: Darci is sole repo owner.
- Periodic rotation policy not established for any key.

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
