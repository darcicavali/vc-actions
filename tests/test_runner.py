"""Tests for scripts/runner.py.

Strategy: stub out the client factories so we never touch the network, then
exercise the orchestration: phase 1 runs all specialists, phase 2 runs the
coordinator, a failing specialist does not block the coordinator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace as dc_replace
from pathlib import Path

import pytest

import scripts.runner as runner_mod
from scripts.claude_client import ClaudeResponse
from scripts.config import Config
from scripts.runner import run_weekly


@dataclass
class StubClaudeClient:
    """Returns a hardcoded specialist response for any prompt, EXCEPT when it
    sees the coordinator schema marker — then it returns the coordinator
    response. Lets one fixture serve both phases."""

    specialist_text: str
    coordinator_text: str
    model: str = "claude-sonnet-4-5-20250929"
    fail_for_agents: set[str] = None
    calls: int = 0

    def complete(self, prompt: str) -> ClaudeResponse:
        self.calls += 1
        # Cheap signal: only the coordinator prompt mentions sequenced_actions.
        is_coord = '"sequenced_actions"' in prompt and '"one_thing_this_week"' in prompt
        # Optional fail-injection by agent role name.
        if self.fail_for_agents:
            for needle in self.fail_for_agents:
                if needle in prompt and not is_coord:
                    raise RuntimeError(f"injected failure: {needle}")
        text = self.coordinator_text if is_coord else self.specialist_text
        return ClaudeResponse(
            text=text,
            input_tokens=1000,
            output_tokens=200,
            model=self.model,
        )


@pytest.fixture
def base_config() -> Config:
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


def _specialist_response() -> str:
    return json.dumps(
        {
            "summary": "specialist summary",
            "diagnosis": "specialist diagnosis",
            "recommendations": [
                {
                    "priority": 1,
                    "action": "do X",
                    "why": "because",
                    "impact_dollars_per_week": 50,
                    "confidence": "medium",
                    "effort": "low",
                    "depends_on": [],
                }
            ],
            "watch_list": ["watch"],
            "data_quality": "medium",
        }
    )


def _coordinator_response() -> str:
    return json.dumps(
        {
            "summary": "coordinator summary.",
            "one_thing_this_week": "do the big thing",
            "pace_status": {
                "ytd_revenue": 67200,
                "target_ytd": 80000,
                "gap": -12800,
                "pace_signal": "behind",
                "weeks_remaining": 34,
                "needed_per_week": 8617,
            },
            "themes": [],
            "sequenced_actions": [
                {
                    "priority": 1,
                    "day": "Monday",
                    "action": "do X",
                    "agent_source": "AdsAgent",
                    "effort": "low",
                    "impact_dollars_per_week": 40,
                    "depends_on": [],
                }
            ],
            "conflicts_resolved": [],
            "watch_list": [],
            "summary_email_body": "the email body",
        }
    )


def _patch_runner(
    monkeypatch,
    sheets,
    base_config,
    prompts_dir,
    *,
    fail_for_agents: set[str] | None = None,
    dry_run: bool = False,
):
    """Patch the runner to use fake sheets + stub Claude, and pin prompts_dir."""
    claude = StubClaudeClient(
        specialist_text=_specialist_response(),
        coordinator_text=_coordinator_response(),
        fail_for_agents=fail_for_agents,
    )

    monkeypatch.setattr(runner_mod, "get_config", lambda: dc_replace(base_config, dry_run=dry_run))
    monkeypatch.setattr(
        runner_mod, "_build_clients", lambda cfg: (claude, sheets)
    )

    # Pin prompts_dir on every constructed agent.
    original_cls_list = list(runner_mod.SPECIALIST_CLASSES)

    def wrap(cls):
        original_init = cls.__init__

        def __init__(self, *args, **kwargs):
            kwargs.setdefault("prompts_dir", prompts_dir)
            original_init(self, *args, **kwargs)

        cls.__init__ = __init__

    for cls in [*original_cls_list, runner_mod.GoalsAgent]:
        wrap(cls)
    return claude


def test_run_weekly_happy_path(monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir):
    _patch_runner(monkeypatch, sheets, base_config, prompts_dir)
    code = run_weekly()
    assert code == 0
    # 7 specialist memos + 1 coordinator memo.
    memo_rows = fake_spreadsheet.worksheet("Agent Memos").get_all_records()
    agents_seen = {r["agent"] for r in memo_rows}
    assert {
        "AdsAgent",
        "CustomerAgent",
        "ProductAgent",
        "ContentAgent",
        "FunnelAgent",
        "FinancialAgent",
        "SEOAgent",
        "GoalsAgent",
    }.issubset(agents_seen)
    plan_rows = fake_spreadsheet.worksheet("Action Plan").get_all_records()
    assert len(plan_rows) == 1


def test_failing_specialist_does_not_block_coordinator(
    monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir
):
    _patch_runner(
        monkeypatch,
        sheets,
        base_config,
        prompts_dir,
        fail_for_agents={"CRM & Lifecycle Specialist"},  # CustomerAgent's role prompt header
    )
    code = run_weekly()
    assert code == 1  # at least one specialist failed
    # Coordinator still ran (its memo + plan row exist).
    plan_rows = fake_spreadsheet.worksheet("Action Plan").get_all_records()
    assert len(plan_rows) == 1
    # Runtime log captured the error.
    rt = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert any(r["agent"] == "CustomerAgent" and r["status"] == "error" for r in rt)


def test_dry_run_writes_nothing(monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir, capsys):
    _patch_runner(monkeypatch, sheets, base_config, prompts_dir, dry_run=True)
    code = run_weekly(dry_run=True)
    assert code == 0
    assert fake_spreadsheet.worksheet("Agent Memos").get_all_records() == []
    assert fake_spreadsheet.worksheet("Action Plan").get_all_records() == []
    assert fake_spreadsheet.worksheet("Runtime Log").get_all_records() == []
    out = capsys.readouterr().out
    assert "[DRY RUN] AdsAgent" in out
    assert "[DRY RUN] GoalsAgent" in out
