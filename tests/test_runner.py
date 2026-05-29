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

    def complete(
        self,
        user_prompt: str,
        *,
        system: list[dict] | str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ClaudeResponse:
        self.calls += 1
        sys_text = ""
        if isinstance(system, list):
            sys_text = "\n".join(b.get("text", "") for b in system)
        elif isinstance(system, str):
            sys_text = system
        combined = f"{sys_text}\n{user_prompt}"
        # Cheap signal: only the coordinator prompt mentions sequenced_actions.
        is_coord = '"sequenced_actions"' in combined and '"one_thing_this_week"' in combined
        # Optional fail-injection by agent role name.
        if self.fail_for_agents:
            for needle in self.fail_for_agents:
                if needle in combined and not is_coord:
                    raise RuntimeError(f"injected failure: {needle}")
        text = self.coordinator_text if is_coord else self.specialist_text
        return ClaudeResponse(
            text=text,
            input_tokens=1000,
            output_tokens=200,
            model=model or self.model,
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
        resend_api_key="",
        resend_from="VC Actions <onboarding@resend.dev>",
        resend_to="",
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
    # Skip the inter-agent sleep in tests (default is 60s × 6 = unusable).
    monkeypatch.setenv("VC_ACTIONS_INTER_AGENT_DELAY_SECONDS", "0")

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
    # 6 specialist memos + 1 coordinator memo (FunnelAgent retired 2026-05-29).
    memo_rows = fake_spreadsheet.worksheet("Agent Memos").get_all_records()
    agents_seen = {r["agent"] for r in memo_rows}
    assert {
        "AdsAgent",
        "CustomerAgent",
        "ProductAgent",
        "ContentAgent",
        "FinancialAgent",
        "SEOAgent",
        "GoalsAgent",
    }.issubset(agents_seen)
    assert "FunnelAgent" not in agents_seen
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


def test_inter_agent_delay_reads_env(monkeypatch):
    monkeypatch.setenv("VC_ACTIONS_INTER_AGENT_DELAY_SECONDS", "5")
    assert runner_mod._inter_agent_delay() == 5
    monkeypatch.setenv("VC_ACTIONS_INTER_AGENT_DELAY_SECONDS", "0")
    assert runner_mod._inter_agent_delay() == 0
    monkeypatch.setenv("VC_ACTIONS_INTER_AGENT_DELAY_SECONDS", "not-a-number")
    assert runner_mod._inter_agent_delay() == runner_mod.DEFAULT_INTER_AGENT_DELAY_SECONDS
    monkeypatch.delenv("VC_ACTIONS_INTER_AGENT_DELAY_SECONDS", raising=False)
    assert runner_mod._inter_agent_delay() == runner_mod.DEFAULT_INTER_AGENT_DELAY_SECONDS


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


def test_bootstrap_only_creates_tabs_without_calling_claude(
    monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir, capsys
):
    claude = _patch_runner(monkeypatch, sheets, base_config, prompts_dir)
    code = run_weekly(bootstrap_only=True)
    assert code == 0
    # No agent ran — no Claude calls at all.
    assert claude.calls == 0
    # Tabs from the schema exist and are header-only.
    assert fake_spreadsheet.worksheet("Agent Memos").get_all_records() == []
    assert fake_spreadsheet.worksheet("Action Plan").get_all_records() == []
    out = capsys.readouterr().out
    assert "bootstrap_only=true" in out
    assert "[DRY RUN]" not in out


def test_list_tabs_prints_titles_without_calling_claude(
    monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir, capsys
):
    claude = _patch_runner(monkeypatch, sheets, base_config, prompts_dir)
    code = run_weekly(list_tabs=True)
    assert code == 0
    # No agent ran — no Claude calls at all.
    assert claude.calls == 0
    out = capsys.readouterr().out
    assert "list_tabs=true" in out
    # Headers from TAB_SCHEMAS land in the output (sheets fixture pre-seeds them).
    assert "Agent Memos" in out
    assert "Action Plan" in out


def test_resend_takes_priority_over_omnisend(
    monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir
):
    """When both Resend AND Omnisend are configured, Resend wins. The runner
    sends one email via Resend and does not call Omnisend."""
    cfg = dc_replace(
        base_config,
        resend_api_key="rk_test",
        resend_to="darci@example.com",
        omnisend_api_key="ok_test",
        omnisend_digest_recipient="darci@example.com",
    )
    _patch_runner(monkeypatch, sheets, cfg, prompts_dir)
    monkeypatch.setattr(runner_mod, "get_config", lambda: cfg)

    sent: list[dict] = []

    class FakeResend:
        def __init__(self, api_key, **_kwargs):
            self.api_key = api_key

        def send_email(self, **kwargs):
            sent.append(kwargs)
            from scripts.resend_client import ResendResult
            return ResendResult(status_code=200, body='{"id":"abc"}')

    class FakeOmnisend:  # should never be constructed
        def __init__(self, *a, **k):
            raise AssertionError("Omnisend must not be called when Resend is set")

    monkeypatch.setattr(runner_mod, "ResendClient", FakeResend)
    monkeypatch.setattr(runner_mod, "OmnisendClient", FakeOmnisend)

    code = run_weekly()
    assert code == 0
    assert len(sent) == 1
    msg = sent[0]
    assert msg["recipient"] == "darci@example.com"
    assert msg["sender"].endswith("onboarding@resend.dev>")
    assert msg["subject"].startswith("VC Weekly Plan")
    assert "ONE THING THIS WEEK" in msg["text"]


def test_no_email_sent_when_neither_provider_is_configured(
    monkeypatch, sheets, fake_spreadsheet, base_config, prompts_dir, capsys
):
    """If both Resend and Omnisend are unset, the run still completes and
    the action plan lands in the sheet — just no email."""
    _patch_runner(monkeypatch, sheets, base_config, prompts_dir)

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("no email provider should be constructed")

    monkeypatch.setattr(runner_mod, "ResendClient", Boom)
    monkeypatch.setattr(runner_mod, "OmnisendClient", Boom)

    code = run_weekly()
    assert code == 0
    out = capsys.readouterr().out
    assert "no email provider configured" in out


def test_test_email_sends_sample_and_exits_without_running_agents(
    monkeypatch, base_config, capsys
):
    """test_email mode hits Resend with a sample plan and exits before any
    agent runs. No Sheets connection needed."""
    cfg = dc_replace(
        base_config,
        resend_api_key="rk_test",
        resend_to="darci@example.com",
    )
    monkeypatch.setattr(runner_mod, "get_config", lambda: cfg)

    sent: list[dict] = []

    class FakeResend:
        def __init__(self, api_key, **_kwargs):
            self.api_key = api_key

        def send_email(self, **kwargs):
            sent.append(kwargs)
            from scripts.resend_client import ResendResult
            return ResendResult(status_code=200, body='{"id":"abc"}')

    monkeypatch.setattr(runner_mod, "ResendClient", FakeResend)
    # If the runner tried to build sheets/Claude, this would explode — proves
    # the early-exit path is taken.
    def boom(*a, **k):
        raise AssertionError("test_email mode must not build clients")
    monkeypatch.setattr(runner_mod, "_build_clients", boom)

    code = run_weekly(test_email=True)
    assert code == 0
    assert len(sent) == 1
    msg = sent[0]
    assert msg["recipient"] == "darci@example.com"
    assert "TEST EMAIL" in msg["text"]
    assert "ONE THING THIS WEEK" in msg["text"]
    out = capsys.readouterr().out
    assert "test_email=true" in out
