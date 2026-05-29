# Build Journal

This file documents the evolution of vc-actions. Each work session adds an entry below.

**Rules:**
- Append-only. Never edit past entries.
- Every session, even small ones, gets an entry.
- Honest about what failed and why — that's the most valuable signal for future sessions.
- Date in `YYYY-MM-DD` format.

---

## 2026-05-11 — Session 0: Spec drafted (pre-build)

### What was attempted
- v1 through v5 spec iterations with Darci
- v4 = multi-agent framework
- v5 = added memory architecture + journaling requirements

### What worked
- Star architecture (specialists → coordinator) chosen over mesh — simpler, debuggable
- Claude API as the reasoning engine per agent — flexible, calibrates over time via memory
- Three memory layers (prompts / episodic / knowledge) — covers all real cases
- Repo created, prompts uploaded as flat files via web (folder structure to be fixed at next push)

### What failed / had to retry
- v1-v3 specs were too rule-based — Darci correctly pushed for agent-driven reasoning
- v2 treated all campaign types equally — wrong; needed to focus on non-customer
- GitHub MCP couldn't auth to write to repo — Darci pushed files manually via web upload

### Decisions made
- 8 total agents (7 specialists + 1 coordinator), including FinancialAgent and SEOAgent
- Drop WhatsApp agent — data too messy
- Drop drops system from this scope (separate repo `vc-drops` for that)
- Claude Sonnet 4.5 as default model
- ~$0.50/week budget acceptable

### Open questions
- Should test_mode be a per-agent flag or global? → defer to runner.py session
- How does coordinator handle a specialist that failed this week? → spec says "skip with warning"
- Should we add a `dry_run` mode that prints memos without writing? → defer

### Learnings for future sessions
- Darci wants concise responses but detailed specs — split the difference: chat short, files thorough
- Memory architecture MUST be in from day 1 — retrofitting it costs more
- Build journal entries are cheap to write and expensive to skip — never skip

---

## 2026-05-11 — Session 1: Cleanup + scaffold + shared infra + BaseAgent + AdsAgent

### Session goal
Per v4 + v5 specs: clean up flat-uploaded prompts, build repo scaffold, shared
infrastructure (config, claude_client, sheets_client, omnisend_client, memory,
journal, runtime_log) with tests, then BaseAgent with memory-aware `run()`,
then AdsAgent (proof-of-concept) with integration test. STOP after that for
review.

### What was attempted (cleanup phase — done)
- Moved 9 role-prompt markdown files from repo root into `prompts/`
  (ads, customer, product, content, funnel, financial, seo, coordinator,
  base_context).
- Created `.env.example` listing all required env vars per v4 §"Manual setup."
- Created `.gitignore` (Python + secrets + tooling).
- No `download` file present, nothing to delete.
- Created empty directory skeleton: `agents/ scripts/ tests/ tests/fixtures/
  .github/workflows/`.

### What was attempted (build phase)
- `scripts/config.py` — dataclass-based, `lru_cache`'d `get_config()`, env-driven.
- `scripts/claude_client.py` — wraps `anthropic.Anthropic`, returns
  `ClaudeResponse(text, input_tokens, output_tokens, model)` so the runtime
  log can capture cost without re-parsing. Strips ```json fences.
- `scripts/sheets_client.py` — gspread-based, centralizes all I/O: tab
  bootstrap with `TAB_SCHEMAS`, memo append/read, lessons read (active +
  scoped + non-expired), outcomes read, runtime log append. Retry on
  `APIError` with exponential backoff.
- `scripts/memory.py` — `load_agent_memory()` + `render_memory_block()`
  produce the deterministic, model-friendly memory text block. Best-effort:
  missing tabs degrade to empty lists.
- `scripts/runtime_log.py` — `RuntimeEntry` dataclass + writer.
- `scripts/journal.py` — `JournalEntry` + `append_entry()` for this very
  journal. Future runtime tooling can use the same writer.
- `scripts/omnisend_client.py` — minimal POST-event client for the digest.
- `agents/base.py` — `BaseAgent` with memory-aware `run()` per v5 §Part 2:
  loads lessons + own memos + outcomes, builds prompt, calls Claude,
  parses JSON, writes memo, ALWAYS writes a runtime log row (ok or error).
- `agents/ads_agent.py` — proof-of-concept specialist: reads the 5 Meta Ads
  tabs, missing tabs degrade to error placeholders in the data block.
- Tests: 34 passing. Real prompts + role file + base_context.md exercised
  in `tests/test_ads_agent.py`. Lesson-honoring, memory-empty, and error-path
  cases are all covered.

### What worked
- Hand-rolled `FakeSpreadsheet`/`FakeWorksheet` fixtures over mocking — the
  tests are behaviorally honest and read like the production code.
- `try/finally` in `BaseAgent.run()` guarantees a Runtime Log row even when
  Claude or sheets writes raise. Inner `try` on the log write itself prevents
  logging failures from masking the real exception.
- `MemoRow`/`LessonRow`/`OutcomeRow` dataclasses give us typed access at the
  consumer side without adding Pydantic.
- Centralizing tab schemas in `TAB_SCHEMAS` lets us `ensure_all_tabs()` for
  bootstrap and re-validate headers if they drift.

### What failed / had to retry
- System-installed `cryptography==41.0.7` panicked at import time
  (`pyo3_runtime.PanicException`) because gspread's auth pulls
  `google-auth` → `cryptography`. Fix: `pip install --force-reinstall
  --ignore-installed cryptography`. Not a code bug, but worth recording for
  any future environment that hits the same Rust ABI mismatch.
- Initial `FakeWorksheet.update` only supported `A1` updates. That's enough
  for ensure_tab; if a future test needs arbitrary-cell writes the fake will
  need extending.

### Decisions made
- **Dataclasses over Pydantic** to match vc-drops style and keep deps minimal.
- **Sequential runs, no async** — 7 agents × ~30s each is fine, and async
  would complicate error isolation per the v4 try/except-per-agent rule.
- **Memory failures degrade to empty lists** rather than aborting the run.
  Acceptance criteria require the empty-memory case to work; same code path
  also covers a transiently flaky sheets read.
- **Claude response cost computed client-side** from a small price table.
  Avoids needing the API's metadata endpoint; price drift will require a
  manual update but cost is tiny.
- **Raw response truncated to 8KB** before writing to the sheet, per v5
  schema. Full response is still on the in-memory `AgentMemo`.
- **`run()` always writes a runtime log row**, even on failure. Status
  column is the distinguishing field.

### Open questions
- `dry_run` mode is in `Config` but not yet honored — defer to the
  `runner.py` session.
- Should `BaseAgent.run()` swallow lesson-loading exceptions and still emit
  a memo, or hard-fail? Currently it hard-fails on `gather_data` errors and
  swallows memory-tab errors. Likely fine; revisit when running live.
- Meta Ads tab names (`Meta Ads Summary` etc.) are assumed from spec — need
  Darci to confirm exact tab names in the dashboard sheet before live run.

### Learnings for future sessions
- The fake-gspread fixture pattern in `tests/conftest.py` is reusable for
  every future specialist agent — keep it generic, do not add agent-specific
  helpers there.
- Use `prompts_dir=...` constructor arg on BaseAgent so tests can point to
  any directory; the default is `scripts/config.PROMPTS_DIR`.
- When wiring the runner, route per-agent `try/except` AROUND `run()`, not
  inside it — coordinator should still see partial state.
- 34 tests, ~0.3s — keep test suite fast and add to it per agent. Don't
  introduce live-network tests in this repo.




---

## 2026-05-11 — Session 2: Remaining specialists + GoalsAgent + runner

### Session goal
After Session 1 was approved, build the other 6 specialist agents
(CustomerAgent, ProductAgent, ContentAgent, FunnelAgent, FinancialAgent,
SEOAgent), then the GoalsAgent coordinator, the runner that orchestrates
the weekly run, the GitHub Actions workflow, and a dry-run mode the user
asked for.

### What was attempted
- Added `dry_run` mode to `BaseAgent` (printable preview, no sheet writes,
  no Runtime Log write). Surfaced as `--dry-run` CLI flag on the runner
  and `VC_ACTIONS_DRY_RUN` env var.
- Extracted shared specialist boilerplate into `BaseAgent.data_tabs` +
  default `gather_data()`. Each specialist is now a ~15-line file that
  declares `name`, `role_prompt_file`, `data_tabs`.
- Built `CustomerAgent`, `ProductAgent`, `ContentAgent`, `FunnelAgent`,
  `FinancialAgent`, `SEOAgent` using that pattern.
- Added a parametrized test (`tests/test_specialists.py`) that runs every
  specialist class through a full `run()` and verifies the prompt file
  exists, tabs land in the prompt, and a memo + Runtime Log row are
  written.
- Built `GoalsAgent` (coordinator). It overrides `gather_data` to read
  this-run specialist memos + Goal Tracker + Weekly Summary; overrides
  `build_prompt` to use the coordinator schema; overrides `parse_response`
  to produce both an `AgentMemo` (for the memory layer to find next week)
  AND an `ActionPlan` dataclass; overrides `write_memo` to append to
  `Agent Memos` and OVERWRITE the `Action Plan` tab.
- Added `SheetsClient.write_action_plan(...)` and tightened
  `FakeWorksheet.update` to handle multi-row replacements.
- Built `scripts/runner.py` with 3 phases: specialists (failure-isolated
  per agent) → coordinator → Omnisend digest email (skipped if not
  configured or in dry-run). CLI entrypoint: `python -m scripts.runner
  [--dry-run]`.
- Added `.github/workflows/weekly_run.yml` — Monday 13:00 UTC cron + a
  manual-trigger button with a dry-run input + a separate test job.
- Tests: 57 passing, ~0.3s. Includes runner happy-path, runner with one
  injected specialist failure (coordinator still runs), and runner
  dry-run (zero sheet writes anywhere).

### What worked
- The single `data_tabs` declaration kept each new specialist tiny.
  Adding agents is now near-free.
- Routing GoalsAgent output through BOTH `Agent Memos` AND `Action Plan`
  means the memory layer "just works" for the coordinator next week —
  no custom loader needed.
- The runner's failure isolation is per-agent `try/except` AROUND `run()`,
  not inside it. Specialists still get their own Runtime Log row on
  failure (BaseAgent's `try/finally` handles that).
- The stub Claude in `tests/test_runner.py` distinguishes specialist vs.
  coordinator prompts by looking for `"sequenced_actions"` in the prompt
  text. Simple and robust without parsing JSON.

### What failed / had to retry
- `FakeWorksheet.update` originally only handled single-row A1 writes
  (sufficient for `ensure_tab`). The Action Plan overwrite is two rows
  (headers + data), so it had to be generalized to replace the whole row
  range. That broke nothing else.
- Initial `test_action_plan_is_overwritten_not_appended` ran without
  prior memos and the coordinator returned 0 memos. Fixed by seeding
  specialist memos via `_seed_specialist_memos` before each run.
- The injected-failure test originally used agent class names as needles
  to detect which prompt to fail. That was unreliable (the class name
  isn't in the prompt). Switched to a fragment of the role prompt
  (`"CRM & Lifecycle Specialist"` — the heading of customer.md).

### Decisions made
- **Dry-run is per-instance with config fallback.** Each agent accepts
  `dry_run=...` in `__init__`; if not passed, falls back to
  `config.dry_run`. This lets the runner force dry-run via CLI while
  still respecting env config.
- **Coordinator writes to BOTH tabs.** `Action Plan` is the structured,
  weekly-overwritten plan; `Agent Memos` gets a coordinator entry so the
  memory layer sees its own history.
- **Action Plan tab is fully overwritten on each write** (header row +
  one data row). Matches v4 spec "overwritten weekly."
- **Runner returns non-zero exit code if any specialist failed.**
  Coordinator failures alone also count. Lets GitHub Actions surface
  red runs.
- **Workflow cron at 13:00 UTC.** That's 8 AM CDT (DST) / 7 AM CST.
  Better than getting 9 AM during DST shoulder. Can be adjusted if Darci
  prefers exactly 8 AM CST.
- **Specialists use the natural tab names from v4 spec verbatim.** User
  confirmed Meta Ads tab names match; the others are best-guess until
  verified against the live `vc-dashboard` sheet. Missing tabs degrade
  to error placeholders, so a mismatch won't crash a run — it'll just
  show up in `data_quality` from Claude.

### Open questions
- Tab name verification for the non-Meta specialists. Best done by
  running `--dry-run` against the real sheet and seeing which tabs come
  back as `{"error": "WorksheetNotFound"}` in the data block.
- Goal Tracker auto-population — spec says it's manually maintained by
  Darci. No bootstrap rows beyond headers. Confirm before first live
  run.
- The Omnisend automation must be created MANUALLY by Darci. The runner
  just triggers an event named `vc_weekly_plan` (configurable); Omnisend
  has to be configured to listen and render the email body from the
  event properties.

### Learnings for future sessions
- A 15-line specialist file is the right size. Don't add logic to them —
  if data needs munging, do it in `BaseAgent` or a helper.
- The "Coordinator memo also lives in Agent Memos" choice pays for
  itself in week 2 — no special-case code in the memory layer.
- For workflow YAML, prefer `vars` for non-secret config (model name,
  recipient email) and `secrets` only for credentials. Easier rotation.

---

## Ops — 2026-05-12 — Session memory system + status reset

### Session goal
Recover after a prior session stalled mid-deploy. Establish a durable
cross-session memory system so future sessions of Claude can pick up where
the last one left off without making Darci re-explain context.

### What was attempted
- Read `BUILD_JOURNAL.md` through Session 2 to ground the current session.
- Confirmed the GitHub Actions workflow is in place and uses GitHub Secrets
  (not the local `.env`), so the prior session's "check your local `.env`"
  terminal path was unnecessary friction for Darci's actual workflow.
- Created `CLAUDE.md` at repo root. Contains: who Darci is, communication
  rules (no terminal, short chats, clear numbered steps), current deployment
  state, open requirements, and the start/end-of-session protocol so any
  future Claude session reads it first and behaves consistently.
- Established the convention: ops entries go at the bottom of this file
  under `## Ops — YYYY-MM-DD — <title>`, append-only, same shape as build
  entries.

### What worked
- The repo's existing `BUILD_JOURNAL.md` discipline made it trivial to
  layer an ops-journal convention on top — no new file, no new format.
- Catching that GitHub Actions already does everything (cron + manual
  trigger + secrets) means Darci does not need a local Python install at
  all. Eliminates an entire class of friction the prior session was
  fighting against.

### What failed / had to retry
- Prior session derailed into PowerShell `.env` diagnostics that left
  Darci's terminal stuck in a `>>` continuation loop. Root cause: pasted
  multi-line snippet with unclosed quotes/braces. Lesson: never hand Darci
  a multi-line shell snippet. If terminal is unavoidable, give a single
  one-liner. Better: don't suggest terminal at all.

### Decisions made
- **No terminal commands** for Darci unless strictly unavoidable. Codified
  in `CLAUDE.md` as a permanent rule.
- **Short chat answers, detailed files.** Same.
- **GitHub Actions web UI is the production interface.** Local Python is
  developer-only and Darci is not the developer.
- **CLAUDE.md is the snapshot, journal is the history.** Update CLAUDE.md's
  "Current state" section every session (overwrite). Append to journal
  every session (never overwrite).
- **Two-way communication (Telegram / desktop chat) is now a formal open
  requirement.** It is not in v4 or v5 spec. Treat as the next thing to
  scope after the first successful dry-run.

### Open questions
- Are the 3 required GitHub secrets actually saved correctly? Darci says
  yes from a prior session; will be confirmed on first dry-run.
- Was the Google Sheet shared as Viewer or Editor? The workflow writes,
  so it needs Editor. README's earlier mention of Viewer is wrong for
  this use case. To verify on first dry-run.
- Two-way comms: Telegram bot vs. a small web chat UI vs. both? What's
  the actual user need — quick mobile pings, deeper desktop sessions, or
  both? Needs a short scoping conversation before any build.

### Next step
1. Darci re-triggers the dry-run from
   https://github.com/darcicavali/vc-actions/actions/workflows/weekly_run.yml
   ("Run workflow" → dry_run = true → green button). The three known
   failures from the first attempt (200k token overflow, rate limits,
   Windows UTF-8) are fixed in main; this run is confirming the fixes.
2. Paste any errors back here. I fix.
3. Once dry-run is green, scope two-way comms (Telegram + desktop chat).

### Correction to current-state snapshot (added after reviewing git history)
The initial CLAUDE.md written this session implied the first dry-run had
not been attempted. Git history shows otherwise: prior sessions did run
it, hit 3 distinct failures, and fixed all of them (commits 535221c,
4ea6c46, 005ae2e). Test count is 62, not 57. CLAUDE.md has been updated
to reflect this. Lesson: always reconcile self-reported state with
`git log` before writing the snapshot.

---

## Ops — 2026-05-12 — Discovered three unmerged PRs of real work

### Session goal
Recover full session state after Darci pasted the transcript of the
session that stalled. Memory files were missing a lot.

### What was attempted
- Read Darci's pasted transcript carefully. It describes three large
  pieces of work (cost cuts, baseline layer, chat bot) that the previous
  session built and "shipped" as PR 3 / PR 4 / PR 5 — but I had not seen
  them in `main` so I had treated the project as just "deploy what's
  there, then build chat later."
- Ran `git branch -a` and `git log --all`. Found three commits sitting on
  `origin/claude/build-multiagent-system-Q4Z6T` that were pushed but never
  merged into `main`:
  - `55fbc73` — Cost cuts (PR 3): prompt caching, Haiku routing for
    Content + SEO, 50→12 rows/tab. ~$0.80/run → ~$0.10–0.15/run.
  - `bb61af9` — Baseline layer (PR 4): `BASELINE: <Agent>` tabs (one per
    agent) carry curated long-run wisdom; `baseline_prompts/` directory +
    `BASELINES.md` operator guide explain the Claude Max workflow for
    refreshing them at zero API cost. Default rows/tab drops 12→4.
  - `87c8270` — Chat bot (PR 5): full `chat/` package — Streamlit web UI
    + Telegram long-polling bot over one shared `brain.py`, SQLite
    conversation memory, `Bot Actions` audit tab, `Bot Notes`
    forward-channel tab, guardrail framework, Dockerfile + fly.toml
    deploy stubs.

### What worked
- Reading the transcript surfaced a new permanent preference: action
  items needed from Darci should always be at the BOTTOM of any chat
  reply, clearly labeled. Captured in CLAUDE.md.
- `git log --all` proved decisive once again — the work isn't lost,
  it's just unmerged.

### What failed / had to retry
- Earlier this session I confidently said "you're one button-click away
  from the next milestone" without realizing three entire PRs of work
  were stranded on an unmerged branch. That was wrong. Lesson: always
  check ALL branches with `git log --all`, not just the current one.
- I told Darci I "couldn't read the public session link." That was
  technically correct (claude.ai needs auth) but didn't matter once she
  pasted the relevant content. Next time: ask for paste sooner rather
  than spending tool calls on retries.

### Decisions made
- Treat `claude/build-multiagent-system-Q4Z6T` as the canonical recent
  branch. It contains the three unmerged commits + everything that was
  later cherry-picked or backported to main.
- The right path forward is ONE PR that lands all three commits onto
  `main` in a single review. Splitting into three separate PRs would
  cost Darci three rounds of clicking through GitHub for no benefit;
  the commits are already cleanly separated in git history.
- I will NOT open that PR without explicit authorization from Darci, per
  the standing instruction.

### Open questions
- Should the unmerged branch land into `main` as a single squash, a
  three-commit merge, or a fast-forward? Darci picks; I default to
  three-commit merge so the cost/baseline/chat boundary stays visible
  in `main`'s history.
- Should the chat bot's audit log live in the same Google Sheet as the
  weekly runner data, or a separate sheet? Current code points it at
  the same sheet (`Bot Actions` tab). Likely correct, will confirm.
- Telegram bot needs two env vars on Darci's laptop: `TELEGRAM_BOT_TOKEN`
  and `TELEGRAM_ALLOWED_USER_ID`. She has to create the bot via
  `@BotFather` on Telegram and get her user ID via `@userinfobot`.
  Phone-only, no terminal.

### Next step
1. Ask Darci to authorize opening a PR for the unmerged branch.
2. After merge, re-trigger dry-run from Actions web UI.
3. After green dry-run, walk Darci through Streamlit-first, Telegram-second.

### Learnings for future sessions
- **Always run `git log --all` and `git branch -a` at session start**, in
  addition to reading CLAUDE.md + the journal. Unmerged branches can
  contain critical work.
- **Action items go at the bottom of every chat reply.** Non-negotiable.
- The previous session's transcript explicitly stated PRs 3/4/5 "landed
  sequentially on `claude/build-multiagent-system-Q4Z6T`" — that wording
  meant "landed on the branch," not "landed on main." Future sessions
  should not assume "PR landed" implies "merged to main" without
  checking.

### Learnings for future sessions
- Always read `CLAUDE.md` first. It is not optional.
- Darci's stated preference: "no terminal, short chats, clear instructions,
  I read slow and don't have much time." Respect this absolutely.
- If a session ends mid-task, the *last commit* on the working branch is
  the recovery point. Pick up there. Do not restart.



---

## Ops — 2026-05-19 to 2026-05-22 — Deployment shakedown + first two baselines

### Session goal
Move from "PR #4 merged" to "system actually producing useful output." This
meant: (a) prove the dry-run works end-to-end with real secrets, (b) get
operator-friendly tools (bootstrap, list_tabs) in place so Darci can run
diagnostics without paying for agent passes, (c) start filling baselines
via her Claude.ai Max subscription.

### What was attempted
- 2026-05-19: Darci triggered the first dry-run after the PR #4 merge. It
  finished green and cost $0.26 — within the $0.10-0.30 estimate but on
  the high end (cache cold, baselines empty, no prior memos to compress
  against).
- Found a real bug: the new tabs (`BASELINE: *`, `Bot Actions`, `Bot Notes`)
  did NOT appear in her sheet after the dry-run. Root cause:
  `ensure_all_tabs()` was gated behind `if not effective_dry_run` in
  `scripts/runner.py`. Dry-run intentionally skipped tab creation, which
  is harmless to do in any mode (idempotent + schema-only).
- Shipped PR #5: moved `ensure_all_tabs()` out of the dry-run guard AND
  added a new `--bootstrap-only` flag + workflow input. Bootstrap mode
  creates tabs and exits before any agent runs — **costs $0**. Darci ran
  it; all 10 new tabs appeared.
- Shipped PR #6: `.github/workflows/deploy_bot.yml` — GitHub Actions
  workflow that runs `flyctl deploy --remote-only` for the Telegram chat
  bot. Triggered manually or on changes to `chat/`, `Dockerfile`,
  `fly.toml`, requirements, or itself. Includes a guard step that fails
  early with a clear pointer to the secrets page if `FLY_API_TOKEN`
  isn't set. Merged but not yet exercised (Darci hasn't done Fly.io
  account + Telegram bot setup).
- Shipped PR #7 (still open): `--list-tabs` flag + workflow input that
  prints every tab title in the spreadsheet and exits. Read-only,
  costs $0. Created so Claude (this session) can see what tabs Darci
  actually has without asking her to screenshot a 53-row tab bar.
  Darci ultimately pasted the list manually instead of running the
  workflow, but the tool is still useful for future sessions.
- Track A (baselines via Claude.ai Max):
  - **AdsAgent baseline filled** 2026-05-19 — 7 sections. Notable
    findings: female 65+ age band wastes ~$2.7k at ROAS 0.57 over the
    modern era; freq>5 on RT-non-cust correlates with CTR drop and ROAS
    halving; current Apr-May creative drought (active warm creatives
    dropped from 10-13/week to 2/week); WhatsApp attribution inflates
    RT-customer ROAS by ~2x.
  - **CustomerAgent baseline filled** 2026-05-22 — 8 sections. Key
    findings: 63.7% of named customers are one-timers; top 5% drive
    51.9% of named revenue; "missing middle" — 2-4-order segment is
    thin (113 customers) and is the natural place to push; retention
    curves all in the 22-27% band (OK per role rubric); 4 sections at
    confidence=low because the export doesn't include order-date
    timestamps, Omnisend flow performance, or demographics.

### What worked
- The Claude.ai Max baseline workflow is genuinely good. Both AdsAgent
  and CustomerAgent outputs were structured, well-cited, and properly
  calibrated (high confidence where data is firm, low where it isn't).
  No re-work needed — both got approved on first review.
- `bootstrap_only` mode + `list_tabs` mode both shipped with one test
  each and 100% pass rate. The pattern of "diagnostic free mode behind
  a CLI flag + workflow input" is reusable; future ops tools can follow
  the same shape.
- Updating CLAUDE.md as the snapshot and adding ops entries to the
  journal worked well — Darci explicitly asked "keep updating the log
  and memory as we progress," confirming the system is doing its job.

### What failed / had to retry
- I initially assumed the merge of PR #4 was the end of the deployment
  work and that re-running the dry-run was "the next button click."
  That was wrong twice: first because the tabs didn't auto-create
  (gated behind dry_run), second because I hadn't read the previous
  session's transcript carefully enough to know what was already built.
  Lesson: reconstruct state from git AND from CLAUDE.md AND ask Darci
  what she remembers — don't take one source as canonical.
- I underestimated the dry-run cost ($0.26 vs $0.10-0.15 expected).
  Reason: caching is cold on a fresh run, AND baselines are empty so
  prompts are still bigger than the long-run target. The $0.10-0.15
  target is real but only once baselines are filled and the cache
  warms over consecutive weeks.

### Decisions made
- **Tab creation runs in every mode now**, not just real runs. Schema
  changes shouldn't require paying for an agent pass to materialize.
- **Diagnostic-only modes are first-class.** `bootstrap_only` and
  `list_tabs` set the precedent: any future op (list memos, audit a
  baseline, dump runtime log) should be reachable via a workflow input
  that costs $0 and doesn't side-effect the sheet.
- **One Claude.ai conversation per agent baseline.** Cleaner context,
  avoids cross-contamination, easier to find when refreshing monthly.
- **Schema gaps (Returns, COGS, Margin Trends, All Products, GBP
  Performance, Search Console Queries, Product Meta) are deferred.**
  Don't fix the agent code or extend the dashboard until after all
  baselines are in and we know what's actually missing vs misnamed.
- **Maintenance-reminder feature deferred to after 3-4 baselines.**
  Need real `last_updated` data to validate the staleness logic.

### Open questions
- Should `All Products` in ProductAgent's `data_tabs` be split into
  `All Product by Type` + `All Product by Vendor` to match Darci's
  sheet, or should the upstream `vc-dashboard` consolidate them?
- Returns data shows median 0% via the customer baseline but a dedicated
  `Returns` tab doesn't exist. Where is returns data actually surfaced
  in the dashboard? Need to verify before the FinancialAgent baseline.
- Telegram bot deployment is technically ready but Darci hasn't started
  Fly.io setup. Should we wait until ALL baselines are in, or run them
  in parallel? Current plan: baselines first because they're
  foundational; Track B kicks off after ~4-5 baselines.

### Next step
1. ProductAgent baseline (next agent up). CSVs: Product by Type,
   Product by Vendor, Monthly Product by Type, Monthly Product by
   Vendor, All Product by Type, All Product by Vendor.
2. Then ContentAgent, FunnelAgent, FinancialAgent, SEOAgent,
   GoalsAgent.
3. After 3-4 baselines: build the maintenance-reminder section in the
   weekly digest.
4. Then exercise Track B (Fly.io + Telegram).

### Learnings for future sessions
- **Always run `git log --all --oneline` AND read the latest 1-2 ops
  entries before responding.** Multiple times this session I had to
  correct myself after discovering state via git that wasn't in
  CLAUDE.md yet.
- **Diagnostic-only modes (no Claude calls, no writes) are gold.**
  Build one any time the operator needs to "just look" at something.
- **Calibrated confidence in baselines matters.** Both AdsAgent and
  CustomerAgent flagged data gaps with confidence=low rather than
  inventing — that honesty makes the weekly agent more trustworthy.
- **Darci's new rule (action items at the bottom of every reply)** is
  honored every message now. Codified in CLAUDE.md.


---

## Ops — 2026-05-25 — Real production run, GoalsAgent fix, Resend integration

### Session goal
Get the system to the point where Monday's auto-run produces a usable
action plan AND delivers it to Darci's inbox without manual intervention.

### What was attempted
- ProductAgent, ContentAgent, FunnelAgent, FinancialAgent, SEOAgent baselines
  all filled via Claude.ai Max (7 of 8 specialist baselines now in the
  sheet; GoalsAgent intentionally deferred until run history accumulates).
- Goal Tracker seeded with one row capturing the $360k stretch goal,
  current YTD ($67.8k), required pace ($124.6k by week 21), and the
  $-56.8k gap — surfaces "behind pace" to GoalsAgent on every run.
- First REAL production run (2026-05-22) triggered. All 7 specialists
  succeeded; GoalsAgent failed parsing its own response — JSON cut off
  mid-string at the 2500-token output cap. Fixed in PR #8 by adding
  `preferred_max_tokens=8000` to GoalsAgent + per-call max_tokens
  override on ClaudeClient.complete().
- Replaced Omnisend with Resend for the digest email (PR #9). Reuses the
  API key Darci already has on her `ig-gbp-sync` repo. Omnisend stays as
  a silent fallback so if Resend ever breaks we don't lose email
  delivery entirely. Plain-text formatter (digest_email.py) optimized
  for phone reading: ONE THING THIS WEEK on top, then SUMMARY,
  PACE STATUS, THIS WEEK'S ACTIONS, WATCH NEXT WEEK.
- Built `test_email` mode (PR #10): workflow_dispatch input that sends
  a sample digest and exits. No agent runs, no Claude calls, no sheet
  writes. Mirrors the bootstrap_only / list_tabs diagnostic pattern.
  Used to verify Resend wiring before Monday's auto-run.
- First test_email run logged "no email provider configured" despite
  Darci having added RESEND_API_KEY and RESEND_TO. Root cause: she
  added RESEND_TO under Secrets, but the workflow reads it via
  `${{ vars.RESEND_TO }}` — secrets and variables are separate
  namespaces in GitHub Actions. After moving RESEND_TO from Secrets to
  Variables, the test email arrived in her inbox.

### What worked
- The first real run validated everything below GoalsAgent end-to-end:
  baseline reads, prompt caching, Haiku routing for Content/SEO, per-agent
  60s pacing, memo writes, runtime log writes. The full pipeline is
  durable.
- Resend was the right call — 20-line client vs Omnisend's automation +
  template + event-listener dance. Reusing the ig-gbp-sync account means
  Darci has one place to manage email infra.
- The test_email diagnostic caught the secret-vs-variable mismatch before
  Monday morning. Without it, Monday's cron would have run successfully
  and the email would have silently failed; Darci would have woken up
  to no notification and assumed the system was broken.
- The "$0 diagnostic workflow input" pattern is paying off: bootstrap_only,
  list_tabs, test_email — three different free verifications, all reachable
  by one click from the Actions tab.

### What failed / had to retry
- GoalsAgent JSON truncation was the most predictable bug we could have
  caught in advance — output limits matter when the schema is large.
  Coordinator output is structurally bigger than specialist memos and
  should have had its own max_tokens override from day one.
- I initially routed Darci to add RESEND_TO as a variable but my
  instructions weren't explicit enough about the secret/variable
  distinction. She landed on the secrets page (which is the same
  sidebar entry) and added it there. Lesson: when telling Darci to
  add anything in GitHub, specify BOTH the page AND the tab/section.

### Decisions made
- **Resend over Omnisend for the digest email.** Marketing-platform
  overhead isn't justified for a single recipient. Omnisend code stays
  but is now a fallback; if Resend env vars are unset, the runner uses
  Omnisend if its env vars are set, else skips email silently.
- **GoalsAgent gets preferred_max_tokens=8000.** ~3x the default. Safe
  headroom for the full plan without inflating per-minute token usage.
  Future agents whose outputs grow can follow the same pattern.
- **test_email mode is a first-class workflow input.** Worth the small
  refactor to _send_digest_email taking a plan directly so test mode
  can call it without spinning up GoalsAgent.
- **GoalsAgent baseline deferred.** It needs 3-4 weeks of real run
  history to find cross-agent patterns. Don't force it now.
- **Schema gap cleanup deferred.** Returns/COGS/Margin Trends/GBP/Search
  Console/Product Meta tabs don't exist in Darci's sheet. Agents handle
  missing tabs gracefully. Defer until we know which gaps actually hurt.

### Open questions
- Will Monday 2026-06-01 auto-run actually deliver a useful action
  plan? Real test of the whole system end-to-end on the cron schedule.
- Track B Phase 1 (Telegram bot creation) — should be straightforward
  but Darci hasn't done @BotFather flow before. Worth being explicit
  about each tap in the Telegram app.
- Should I quietly fix the workflow to read RESEND_TO from either
  secret OR variable? Darci said "no need to change that now" — defer
  unless someone else hits the same trap.

### Learnings for future sessions
- **GitHub Secrets ≠ GitHub Variables.** Two separate namespaces under
  the same Settings → Secrets and variables → Actions page. The
  workflow reads `${{ secrets.X }}` for secrets and `${{ vars.X }}` for
  variables. When telling Darci to add anything in GitHub, always
  specify which TAB on that page (Secrets vs Variables).
- **The $0 diagnostic mode pattern is gold.** Every operationally-relevant
  thing should have a "just verify this works" workflow input — costs
  nothing, catches bugs early, doesn't require running the full pipeline.
- **Coordinator output is structurally bigger than specialist output.**
  Anything that aggregates across N agents will produce N× more JSON.
  Set max_tokens accordingly from the start.
- **Calibrated confidence (high/medium/low) in baselines was the right
  call.** All 7 specialist baselines flagged data gaps honestly via
  confidence=low rather than inventing — that honesty is what makes the
  weekly agent trustworthy.
- **Action items at the bottom of every chat reply (Darci's standing
  rule)** is being honored consistently across this whole session.

### Next step
1. Walk Darci through Track B Phase 1 (Telegram bot via @BotFather +
   user ID via @userinfobot — all in the Telegram app, no terminal).
2. Then Phase 2 (Fly.io account + secrets + API token).
3. Then Phase 3 (click Deploy Bot workflow).
4. Monday 2026-06-01: first scheduled auto-run.


---

## Ops — 2026-05-25 (eve) — Chat bot deployed and live

### Session goal
Land Track B: get the Telegram chat bot deployed end-to-end and
responding to Darci's messages. From "code merged but not running" to
"bot is alive."

### What was attempted
- Track B Phase 1: Darci created the bot via @BotFather and grabbed her
  user ID via @userinfobot. Tokens stored separately, not yet wired to
  GitHub.
- Track B Phase 2: Darci tried Fly's "Launch an App from GitHub" UI.
  Hit a generic "Failed to create app. Please try again." error — Fly's
  GitHub-integrated launch flow is flaky and gives no useful detail.
- Pivoted: rewrote `.github/workflows/deploy_bot.yml` to be self-contained.
  Workflow now (PR #11):
  1. Verifies all required secrets are present (clear error if missing)
  2. Parses the app name from fly.toml
  3. Creates the Fly app if it doesn't exist (idempotent)
  4. Stages all Fly secrets from GitHub secrets (--stage avoids early redeploy)
  5. Runs `flyctl deploy --remote-only`
- Darci added FLY_API_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
  as GitHub repo secrets. Triggered deploy. It succeeded.
- Bot still didn't respond. Fly logs showed an ImportError loop —
  `chat/telegram_app.py` and `chat/web_app.py` imported `load_config`
  from `scripts.config`, but the function is `get_config`. Tests for the
  chat package only cover brain/tools/memory/audit/guardrails — the two
  transport entry points are uncovered, so this slipped through. Fixed
  in PR #12.
- After PR #12 merged, deploy auto-ran (chat/** path trigger). New image
  built and prepared, but the previously crash-looping machine had hit
  Fly's max-restart-count of 10 and remained suspended. New machines
  were created but not started.
- Then discovered TWO machines existed (Fly's default for non-HTTP
  process groups). Telegram only allows one long-poller per bot token,
  so having two machines breaks bot replies even if both run cleanly.
  Darci deleted one machine via Fly dashboard and started the other.
  Bot replied to "hi" immediately after.

### What worked
- The self-contained deploy workflow (PR #11) is the right shape:
  one click does everything, no Fly UI required, no terminal. Future
  bot redeploys are a single button click.
- Diagnostic flow scaled: Fly's Logs & Errors page gave us exactly the
  ImportError stack trace we needed. The "machine has reached its max
  restart count" line told us why the new image wasn't being used.

### What failed / had to retry
- The `load_config` vs `get_config` import mismatch should never have
  shipped. Two missing tests would have caught it: a smoke test that
  just imports `chat.telegram_app` and `chat.web_app` (no execution
  needed). Adding these is a small follow-up.
- The Fly Launch UI was a dead end. Spent ~15 minutes there with no
  diagnostic value. Lesson: when Fly's GitHub-integrated UI fails,
  immediately fall back to CLI-via-Actions instead of debugging the UI.
- The dual-machine issue is the second time Fly's defaults conflicted
  with our use case (first was the missing internal port — irrelevant
  for long-polling). For Telegram bots specifically, fly.toml needs a
  hard `count = 1` constraint. Follow-up: add `flyctl scale count 1`
  to the deploy workflow as a final step, OR pin via fly.toml if Fly
  supports that for non-HTTP apps.

### Decisions made
- **Deploy workflow is the canonical bot-deploy path.** Never use Fly's
  Launch UI again. All deploys go through GitHub Actions.
- **Append-only writes for the chat bot.** Current tools (`add_lesson`,
  `note_for_next_run`) cannot delete or modify existing data. Any
  destructive tool added in the future MUST go through the guardrail
  confirmation gate. No exceptions.
- **Single Fly machine, not two.** Telegram's one-poller-per-token rule
  makes multi-machine redundancy harmful, not helpful. Operational
  follow-up: enforce count=1 in the deploy workflow.

### Open questions
- Should I push a fly.toml or deploy-workflow fix to lock count=1?
  Manual delete worked this time but if a future deploy creates two
  machines again, the bot will silently break.
- Anthropic API spend: no cap currently configured on the API key.
  Heavy chat usage could exceed expected $5-30/month range without
  warning. Worth surfacing as an "add this safety net" recommendation.
- Resend free tier covers 3K emails/month; even daily bot-pushed
  digests are nowhere near that limit. Domain verification (custom
  from-address instead of onboarding@resend.dev) deferred until Darci
  wants it.

### Next step
1. Bot is alive — Monday 2026-06-01 is the first scheduled cron with
   email delivery.
2. Push fly.toml/workflow update to lock count=1 (defensive).
3. After Monday's run, decide on next iteration based on real action
   plan output.

### Learnings for future sessions
- **Always smoke-test transport entry points.** If a module is only
  loaded at runtime (like the chat transports), add at least an
  `import chat.telegram_app` test so import errors fail in CI.
- **Fly Machines API quirks:** non-HTTP process groups default to 2
  machines; Telegram bots need exactly 1. Hard-code count=1 in any
  long-polling bot deploy.
- **Fly's Launch UI failures are dead ends.** Use CLI-via-Actions
  instead. The CLI gives actionable errors; the UI gives "Please try
  again."
- **The "machine has reached max restart count" signal** means the
  previous deploy crashed too many times. After fixing the bug, the
  machine still needs a manual restart (the auto-restart counter
  doesn't reset on new image pulls).
- **Telegram allows exactly ONE long-poller per bot token.** This
  invariant means horizontal scaling is structurally impossible for
  this transport. Webhook-based bots can scale; long-polling cannot.
