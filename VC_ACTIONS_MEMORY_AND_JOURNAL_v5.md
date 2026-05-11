# vc-actions — v5 Addendum: Memory Architecture + Build Journaling

**Status:** Additive to v4 spec. Do not skip — these are required from day 1.
**Why this exists:** Without memory, agents repeat mistakes weekly. Without journaling, future build sessions lose context.

---

## Part 1: Memory Architecture

Three layers. Each addresses a different kind of learning.

### Layer 1: Static prompts (manual updates, rare)
Already in v4. `prompts/*.md` files are updated manually when fundamentals change. Git commit propagates.

### Layer 2: Episodic memory (auto-accumulating)

Three new sheet tabs that the system writes to and reads from automatically.

#### `Agent Memos` tab (already in v4 — schema confirmed here)

Headers in order:
```
generated_at, agent, summary, diagnosis, recommendations_json,
watch_list_json, data_quality, raw_response_truncated
```

- Append-only. One row per agent per weekly run.
- `raw_response_truncated`: full Claude response capped at 8000 chars (for debugging without bloating sheet)

Each agent reads its **own last 4 weeks** of memos before analyzing.

#### `Outcomes` tab — Darci marks results

Headers in order:
```
plan_week_start, action_id, source_agent, action_summary,
executed, executed_when, observed_outcome, projected_impact_usd,
actual_impact_usd, learning_note
```

- `plan_week_start`: the week the recommendation was made
- `action_id`: unique ID from the coordinator's plan
- `source_agent`: which specialist's memo led to this action
- `executed`: Y / N / partial
- `observed_outcome`: free text — what actually happened
- `projected_impact_usd`: from the original recommendation
- `actual_impact_usd`: Darci's estimate of real impact
- `learning_note`: free text — anything to remember

Darci fills this throughout the week or end of week.

Each agent reads outcomes of **its own past recommendations** before analyzing — this is how it calibrates confidence.

#### `Runtime Log` tab — auto-written each Monday run

Headers in order:
```
run_at, agent, status, duration_seconds, input_tokens, output_tokens,
cost_usd, key_insight, errors
```

- Used to monitor system health, cost drift, agent failures
- `key_insight`: 1-sentence summary of the most important thing the agent flagged
- `errors`: any exceptions or warnings

### Layer 3: Knowledge memory — Darci's lessons

#### `Agent Knowledge` tab — write-anytime by Darci

Headers in order:
```
added_at, agent_target, category, lesson, active, expires_at, source_notes
```

- `agent_target`: "ALL" or specific agent name (`AdsAgent`, `ProductAgent`, etc.)
- `category`: free text — `vendor`, `strategy`, `timing`, `customer`, `financial`, etc.
- `lesson`: the lesson statement (the actual instruction)
- `active`: TRUE / FALSE — Darci can deprecate without deleting
- `expires_at`: optional date — for time-bound lessons (e.g., "Cash position is tight in May — preserve over scale")
- `source_notes`: where this came from

**Examples:**

| added_at | agent_target | category | lesson | active | expires_at |
|---|---|---|---|---|---|
| 2026-05-11 | AdsAgent | vendor | Maria Brand has 60% return rate — don't recommend reorder regardless of velocity | TRUE | |
| 2026-05-11 | ALL | strategy | No TikTok ads ever — Vanessa won't engage that platform | TRUE | |
| 2026-05-11 | ContentAgent | timing | Brazilian audience peaks Wed/Sun 9pm CT | TRUE | |
| 2026-05-11 | ALL | financial | Cash position is tight — preserve over scale | TRUE | 2026-06-30 |
| 2026-05-11 | CustomerAgent | customer | Don't recommend automated win-back to customers tagged 'wholesale' — they're B2B | TRUE | |

Each agent reads its own lessons + ALL-targeted lessons (active, not expired) before analyzing. **Lessons are treated as hard rules, not suggestions.**

---

## Part 2: Updated agent run flow

Every agent's `run()` method now follows this order:

```python
def run(self) -> AgentMemo:
    # 1. Load static context
    base_context = self._load_base_context()
    role_prompt = self._load_role_prompt()

    # 2. Load memory layers
    lessons = self._load_active_lessons()        # NEW
    own_memos_4w = self._load_own_memos(weeks=4)  # NEW
    outcomes_4w = self._load_outcomes(weeks=4)    # NEW

    # 3. Load this week's data
    data = self.gather_data()

    # 4. Build prompt with all context
    prompt = self._build_prompt(
        base_context, role_prompt, lessons,
        own_memos_4w, outcomes_4w, data
    )

    # 5. Call Claude (instrument timing + tokens)
    start = time.time()
    response = self.claude.complete(prompt)
    duration = time.time() - start

    # 6. Parse + write
    memo = self._parse_response(response)
    self._write_memo(memo)
    self._write_runtime_log(duration, response.usage)  # NEW

    return memo
```

## Part 3: Memory awareness in prompts

Append to `prompts/base_context.md` (applies to all specialists):

```markdown
## Memory awareness — read carefully

Before producing this week's analysis, you will be given:

1. **Active lessons from Darci** — your specific lessons + ALL-agent lessons.
   TREAT THESE AS HARD RULES. If a lesson says "don't recommend X,"
   don't recommend X, regardless of what the data suggests.

2. **Your own memos from the last 4 weeks** — for continuity and avoiding
   contradicting yourself. If you recommended X last week and the situation
   hasn't changed, don't suddenly recommend the opposite.

3. **Outcomes of your past recommendations** — Darci's notes on what
   actually happened. CALIBRATE YOUR CONFIDENCE based on this.
   If you've been over-projecting impact by 2x, scale down future projections.

## In your "diagnosis" section, briefly note (1 sentence each, only if relevant):

- Did last week's recommendation pan out as expected?
- Are you adjusting confidence based on past performance?
- Any lessons that triggered you to avoid a recommendation the data otherwise suggested?
```

For `prompts/coordinator.md`, append:

```markdown
## Memory awareness — coordinator-specific

You also have access to:
- The last 4 weeks of YOUR OWN coordinator plans
- The last 4 weeks of outcomes across all agents
- Active lessons targeted at ALL or at GoalsAgent

When you identify themes or sequence actions:
- Check if you proposed similar moves recently — if so, why didn't they work?
- Honor lessons strictly (e.g., if "no TikTok" is a lesson, drop any
  specialist's TikTok recommendation regardless of merit)
- If you're projecting impact, compare to actual impacts from past weeks
  and discount accordingly
```

---

## Part 4: Build Journal — for Claude Code

Claude Code maintains `BUILD_JOURNAL.md` at repo root. **Append-only.** Each work session adds a dated entry.

### Required format

```markdown
# Build Journal

This file documents the evolution of vc-actions. Each work session adds
an entry below. Append-only — never edit past entries.

---

## YYYY-MM-DD — Session N: Brief description

### What was attempted

- Bullet 1
- Bullet 2

### What worked

- What went well, design choices that paid off

### What failed / had to retry

- Specific problem → resolution
- Failed approach + why it failed

### Decisions made

- Architectural / design decisions + rationale
- Tradeoffs accepted

### Open questions

- Things deferred or unresolved

### Learnings for future sessions

- Patterns to repeat
- Patterns to avoid
- Environment quirks discovered

---

## (next session below)
```

### When Claude Code writes to the journal

- **Start of session:** create a new entry header with date + session goal
- **During session:** add notes inline as decisions or surprises happen
- **End of session:** finalize the entry, summarize learnings

### Example entry

```markdown
## 2026-05-11 — Session 1: Repo scaffold + shared infra

### What was attempted
- BaseAgent class with abstract gather_data() and concrete run()
- SheetsClient adapted from vc-drops
- ClaudeClient wrapper

### What worked
- Dataclass-based AgentMemo (no Pydantic dependency)
- Direct retry decorator for sheets calls
- Loading prompts as plain markdown files

### What failed / had to retry
- First attempt used model="claude-sonnet-4" — failed, real string is "claude-sonnet-4-5-20250929"
- Sheets retry caused infinite loop in test mocks — fixed by exception-type filtering

### Decisions made
- Used dataclasses over Pydantic to keep deps light (matches vc-drops style)
- AgentMemo.raw_response truncated to 8KB before writing to sheet
- Decided AGAINST async — sequential agent runs are fine at 7 × ~30s each

### Open questions
- Should there be a "dry run" mode? Probably yes — defer to runner.py session.
- How should coordinator handle a missing memo? Skip with warning, document in coordinator memo.

### Learnings for future sessions
- gspread + service account is sufficient; don't add google-api-python-client
- Claude wraps JSON in ```json sometimes — strip in parser
- Importing anthropic SDK is fine but pin version (>=0.39.0)
```

### Why this matters

- **Future Darci** opens the repo in 3 months and sees the WHY of design choices
- **Future Claude Code** picks up mid-build without re-discovering dead ends
- **Future me** debugging a regression can see what changed and when
- Real engineering process > working but undocumented code

---

## Part 5: Updated module list

Add to `scripts/`:

- `memory.py` — load active lessons, past memos, past outcomes for an agent
- `journal.py` — read/write build journal entries (Claude Code uses this)
- `runtime_log.py` — write per-agent runtime metrics

Update `scripts/sheets_client.py`:
- Add `read_lessons_for_agent(agent_name)` helper
- Add `read_memos_for_agent(agent_name, weeks_back)` helper
- Add `read_outcomes_for_agent(agent_name, weeks_back)` helper
- Add `append_runtime_log(...)` helper

---

## Part 6: Updated sheet bootstrap

On first run, `ensure_all_tabs()` must create:

- `Agent Memos` (already in v4)
- `Action Plan` (already in v4)
- `Goal Tracker` (already in v4)
- `Agent Knowledge` (NEW)
- `Outcomes` (NEW)
- `Runtime Log` (NEW)

Pre-populate `Agent Knowledge` with 2-3 starter rows that Darci can edit:

```
| 2026-05-11 | ALL | strategy | This is an example lesson. Darci edits, adds, or deactivates lessons here. | TRUE | |
```

---

## Part 7: Updated acceptance criteria

1. **Memory tabs auto-created** on first run with correct headers.
2. **Agent memo MUST reference past context** — if last 4 weeks of memos exist, agent's diagnosis section should reference prior recommendations.
3. **Lessons MUST be honored** — write a test where a lesson says "never recommend X" and the agent receives data that would normally trigger X; verify X is not recommended.
4. **Outcomes feedback loop verified** — write a test where a past recommendation's `actual_impact_usd` is much lower than `projected_impact_usd`, and verify the agent's new recommendation has reduced confidence.
5. **Build Journal exists** at repo root, with entries from every session.
6. **Runtime Log captures** per-agent duration, tokens, cost for every weekly run.

---

## Part 8: Updated build order

| Step | What | Hours |
|---|---|---|
| 1 | Repo scaffold + shared infra (config, clients, utils, **journal, memory, runtime_log**) | 3 |
| 2 | `agents/base.py` with memory-aware `run()` | 2 |
| 3 | AdsAgent + integration test | 1.5 |
| 4 | CustomerAgent + ProductAgent | 2 |
| 5 | ContentAgent + FunnelAgent | 2 |
| 6 | FinancialAgent + SEOAgent | 2 |
| 7 | GoalsAgent (Coordinator) | 2 |
| 8 | `runner.py` + workflow + bootstrap | 1 |
| 9 | End-to-end live test + prompt tuning | 2 |

**Total: ~17.5 focused hours** (+1.5h from v4 for memory infra)

---

## Part 9: Migration notes for Claude Code

If this spec replaces or evolves v4:

1. **Don't skip Build Journal from day 1** — first commit message must reference creating BUILD_JOURNAL.md.
2. **Don't skip memory bootstrap** — every BaseAgent.run() must call `_load_active_lessons()`, `_load_own_memos()`, `_load_outcomes()` even if those tabs are empty.
3. **Test the empty-memory case** — verify everything works on the very first run when no prior memos / outcomes / lessons exist.

End of v5 addendum.
