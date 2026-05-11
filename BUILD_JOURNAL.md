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

## (next session below)
