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
1. Darci triggers the first dry-run from
   https://github.com/darcicavali/vc-actions/actions/workflows/weekly_run.yml
   ("Run workflow" → dry_run = true → green button).
2. Paste any errors back here. I fix.
3. Once dry-run is green, scope two-way comms (Telegram + desktop chat).

### Learnings for future sessions
- Always read `CLAUDE.md` first. It is not optional.
- Darci's stated preference: "no terminal, short chats, clear instructions,
  I read slow and don't have much time." Respect this absolutely.
- If a session ends mid-task, the *last commit* on the working branch is
  the recovery point. Pick up there. Do not restart.

