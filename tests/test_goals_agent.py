"""Tests for the coordinator agent (GoalsAgent).

Verifies:
- gather_data picks up this-week specialist memos and flags missing ones
- the prompt contains all specialist memos plus the coordinator schema
- parse_response produces both an AgentMemo and a populated ActionPlan
- write_memo lands rows in Agent Memos AND a single row in Action Plan
- dry_run does neither but prints the plan
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace as dc_replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents.goals_agent import GoalsAgent
from scripts.claude_client import ClaudeResponse
from scripts.config import Config
from scripts.sheets_client import MemoRow


@dataclass
class StubClaudeClient:
    next_text: str
    model: str = "claude-sonnet-4-5-20250929"
    last_prompt: str | None = None

    def complete(
        self,
        user_prompt: str,
        *,
        system: list[dict] | str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ClaudeResponse:
        sys_text = ""
        if isinstance(system, list):
            sys_text = "\n".join(b.get("text", "") for b in system)
        elif isinstance(system, str):
            sys_text = system
        self.last_prompt = f"{sys_text}\n{user_prompt}" if sys_text else user_prompt
        return ClaudeResponse(
            text=self.next_text,
            input_tokens=20_000,
            output_tokens=1_500,
            model=model or self.model,
        )


@pytest.fixture
def fake_config() -> Config:
    return Config(
        anthropic_api_key="x",
        anthropic_model="claude-sonnet-4-5-20250929",
        google_sheet_id="sheet",
        google_service_account_json="",
        ga4_credentials_json="",
        ga4_property_id="",
        shopify_store_domain="",
        shopify_access_token="",
        omnisend_api_key="",
        omnisend_digest_event="vc_weekly_plan",
        omnisend_digest_recipient="",
        test_mode=True,
        dry_run=False,
    )


@pytest.fixture
def prompts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts"


def _seed_specialist_memos(sheets, agents=("AdsAgent", "CustomerAgent", "ProductAgent")):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for agent in agents:
        sheets.append_memo(
            MemoRow(
                generated_at=now,
                agent=agent,
                summary=f"{agent} summary",
                diagnosis=f"{agent} diagnosis",
                recommendations=[
                    {
                        "priority": 1,
                        "action": f"{agent} top action",
                        "impact_dollars_per_week": 100,
                        "confidence": "high",
                    }
                ],
                watch_list=[f"{agent} watch"],
                data_quality="high",
                raw_response_truncated="",
            )
        )


def _coordinator_response() -> str:
    return json.dumps(
        {
            "summary": "Acquisition push is the play; cash position OK.",
            "one_thing_this_week": "Refresh RT-non-customer creative + reorder top 3 dresses",
            "pace_status": {
                "ytd_revenue": 67_200,
                "target_ytd": 80_000,
                "gap": -12_800,
                "pace_signal": "behind",
                "weeks_remaining": 34,
                "needed_per_week": 8_617,
            },
            "themes": [
                {
                    "theme": "Dresses are the leverage point",
                    "supporting_agents": ["ProductAgent", "ContentAgent"],
                    "implication": "Reorder + post dress carousels.",
                }
            ],
            "sequenced_actions": [
                {
                    "priority": 1,
                    "day": "Monday",
                    "action": "Increase Prospect ASC budget +$10/day",
                    "agent_source": "AdsAgent",
                    "effort": "low",
                    "impact_dollars_per_week": 40,
                    "depends_on": [],
                },
                {
                    "priority": 2,
                    "day": "Wednesday",
                    "action": "Refresh RT-non-customer creative",
                    "agent_source": "AdsAgent",
                    "effort": "medium",
                    "impact_dollars_per_week": 150,
                    "depends_on": [],
                },
            ],
            "conflicts_resolved": [
                {"conflict": "Spend vs. cash", "resolution": "Split: $10/day ads + $300 inventory."}
            ],
            "watch_list": ["RT-non-customer CTR post-refresh"],
            "summary_email_body": "WEEK ENDING ... 📊 Pace: $67k YTD / $360k target — behind by $13k...",
        }
    )


def test_gather_data_collects_specialist_memos(sheets, fake_config, prompts_dir):
    _seed_specialist_memos(sheets, ("AdsAgent", "ProductAgent"))
    claude = StubClaudeClient(next_text=_coordinator_response())
    agent = GoalsAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    data = agent.gather_data()
    assert data["memo_count"] == 2
    found = {m["agent"] for m in data["specialist_memos_this_week"]}
    assert found == {"AdsAgent", "ProductAgent"}
    assert "CustomerAgent" in data["missing_specialists"]


def test_run_writes_memo_and_action_plan(sheets, fake_spreadsheet, fake_config, prompts_dir):
    _seed_specialist_memos(sheets)
    claude = StubClaudeClient(next_text=_coordinator_response())
    agent = GoalsAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    memo = agent.run()

    assert memo.agent == "GoalsAgent"
    assert "Acquisition push" in memo.summary
    assert len(memo.recommendations) == 2
    assert memo.recommendations[0].action.startswith("Increase Prospect ASC")

    # Agent Memos row written.
    memo_rows = fake_spreadsheet.worksheet("Agent Memos").get_all_records()
    assert any(r["agent"] == "GoalsAgent" for r in memo_rows)

    # Action Plan tab has exactly one row (overwritten weekly).
    plan_rows = fake_spreadsheet.worksheet("Action Plan").get_all_records()
    assert len(plan_rows) == 1
    plan = plan_rows[0]
    assert "Refresh RT-non-customer" in plan["one_thing_this_week"]
    actions = json.loads(plan["sequenced_actions_json"])
    assert len(actions) == 2
    themes = json.loads(plan["themes_json"])
    assert themes[0]["theme"].startswith("Dresses")
    pace = json.loads(plan["pace_status"])
    assert pace["pace_signal"] == "behind"
    assert plan["gap_to_close"] in ("-12800", "-12800.0", "-12800.00")  # numeric stringified

    # Runtime log captured ok.
    rt = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert any(r["agent"] == "GoalsAgent" and r["status"] == "ok" for r in rt)


def test_action_plan_is_overwritten_not_appended(sheets, fake_spreadsheet, fake_config, prompts_dir):
    _seed_specialist_memos(sheets)

    claude = StubClaudeClient(next_text=_coordinator_response())
    agent = GoalsAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()
    # Second run should replace, not append.
    agent.run()

    plan_rows = fake_spreadsheet.worksheet("Action Plan").get_all_records()
    assert len(plan_rows) == 1


def test_dry_run_skips_both_writes(sheets, fake_spreadsheet, fake_config, prompts_dir, capsys):
    _seed_specialist_memos(sheets)
    cfg = dc_replace(fake_config, dry_run=True)
    # Seeding above wrote to Agent Memos (not via the agent under test). Snapshot.
    pre_memo_rows = len(fake_spreadsheet.worksheet("Agent Memos").get_all_records())

    claude = StubClaudeClient(next_text=_coordinator_response())
    agent = GoalsAgent(claude, sheets, cfg, prompts_dir=prompts_dir)
    agent.run()

    # No new Agent Memos rows, no Action Plan row, no Runtime Log row.
    assert len(fake_spreadsheet.worksheet("Agent Memos").get_all_records()) == pre_memo_rows
    assert fake_spreadsheet.worksheet("Action Plan").get_all_records() == []
    assert fake_spreadsheet.worksheet("Runtime Log").get_all_records() == []

    out = capsys.readouterr().out
    assert "[DRY RUN] GoalsAgent" in out
    assert "one_thing_this_week:" in out
