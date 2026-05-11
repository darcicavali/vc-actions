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



