"""Tests for BaseAgent.

Strategy: a `StubAgent` subclass + a `StubClaudeClient` that returns
pre-canned responses. We assert:
  - empty memory case works (first ever run)
  - lessons are surfaced in the prompt
  - past memos + outcomes are surfaced in the prompt
  - successful run writes a memo row + a runtime log row
  - failed run still writes a runtime log row with status=error
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents.base import AgentMemo, BaseAgent, Recommendation
from scripts.claude_client import ClaudeResponse
from scripts.config import Config
from scripts.sheets_client import MemoRow


@dataclass
class StubClaudeClient:
    next_text: str = "{}"
    model: str = "claude-sonnet-4-5-20250929"
    input_tokens: int = 100
    output_tokens: int = 50
    last_prompt: str | None = None
    last_system: list[dict] | str | None = None
    last_user_message: str | None = None
    last_model: str | None = None
    last_max_tokens: int | None = None
    raise_exc: Exception | None = None

    def complete(
        self,
        user_prompt: str,
        *,
        system: list[dict] | str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ClaudeResponse:
        self.last_user_message = user_prompt
        self.last_system = system
        self.last_model = model
        self.last_max_tokens = max_tokens
        # last_prompt = combined view so existing substring assertions keep working.
        sys_text = ""
        if isinstance(system, list):
            sys_text = "\n".join(b.get("text", "") for b in system)
        elif isinstance(system, str):
            sys_text = system
        self.last_prompt = f"{sys_text}\n{user_prompt}" if sys_text else user_prompt
        if self.raise_exc is not None:
            raise self.raise_exc
        return ClaudeResponse(
            text=self.next_text,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            model=model or self.model,
        )


class StubAgent(BaseAgent):
    name = "AdsAgent"
    role_prompt_file = "ads.md"

    def __init__(self, *args, gathered_data: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = gathered_data or {"sample": 1}

    def gather_data(self) -> dict:
        return self._data


@pytest.fixture
def fake_config(monkeypatch) -> Config:
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


def _good_response_json() -> str:
    return json.dumps(
        {
            "summary": "Cold prospecting healthy, RT-non-customer fatigued.",
            "diagnosis": "Prospect ASC CPM stable, CTR steady. RT-non-customer freq 3.54, CTR down 18% w/w.",
            "recommendations": [
                {
                    "priority": 1,
                    "action": "Refresh RT-non-customer creative",
                    "why": "Frequency 3.54, CTR -18% w/w — classic creative fatigue.",
                    "impact_dollars_per_week": 120,
                    "confidence": "high",
                    "effort": "medium",
                    "depends_on": [],
                },
                {
                    "priority": 2,
                    "action": "Scale Prospect ASC +$10/day",
                    "why": "Stable CPM, ATC 4.2% — room to scale safely.",
                    "impact_dollars_per_week": 40,
                    "confidence": "medium",
                    "effort": "low",
                    "depends_on": [],
                },
            ],
            "watch_list": ["RT-non-customer post-refresh CTR", "Prospect ASC freq trend"],
            "data_quality": "high",
        }
    )


def test_run_empty_memory_writes_memo_and_runtime_log(sheets, fake_config, prompts_dir, fake_spreadsheet):
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    memo = agent.run()

    assert isinstance(memo, AgentMemo)
    assert memo.agent == "AdsAgent"
    assert len(memo.recommendations) == 2
    assert memo.recommendations[0].priority == 1
    assert memo.data_quality == "high"

    # memo persisted
    memo_rows = fake_spreadsheet.worksheet("Agent Memos").get_all_records()
    assert len(memo_rows) == 1
    assert memo_rows[0]["agent"] == "AdsAgent"
    assert memo_rows[0]["summary"].startswith("Cold prospecting")

    # runtime log persisted with ok status
    rt_rows = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert len(rt_rows) == 1
    assert rt_rows[0]["agent"] == "AdsAgent"
    assert rt_rows[0]["status"] == "ok"
    assert rt_rows[0]["input_tokens"] == 100
    assert rt_rows[0]["output_tokens"] == 50

    # prompt contains memory section even when empty
    assert "(no active lessons)" in claude.last_prompt
    assert "(no prior memos)" in claude.last_prompt
    assert "(no recorded outcomes)" in claude.last_prompt
    # data block is present
    assert '"sample": 1' in claude.last_prompt


def test_run_includes_lessons_and_past_memos_in_prompt(sheets, fake_config, prompts_dir):
    today = datetime.now(timezone.utc).date().isoformat()
    sheets.append_row(
        "Agent Knowledge",
        [today, "AdsAgent", "vendor", "no Maria reorder", "TRUE", "", ""],
    )
    sheets.append_row(
        "Agent Knowledge",
        [today, "ALL", "strategy", "no TikTok ads", "TRUE", "", ""],
    )
    sheets.append_memo(
        MemoRow(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            agent="AdsAgent",
            summary="last week summary",
            diagnosis="last week dx",
            recommendations=[{"priority": 1, "action": "scale ASC", "impact_dollars_per_week": 40, "confidence": "high"}],
            watch_list=[],
            data_quality="high",
            raw_response_truncated="",
        )
    )
    sheets.append_row(
        "Outcomes",
        [today, "a1", "AdsAgent", "scale ASC", "Y", today, "no lift", 200, 50, "over-projected"],
    )

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()

    p = claude.last_prompt
    assert "no Maria reorder" in p
    assert "no TikTok ads" in p
    assert "last week summary" in p
    assert "over-projected" in p


def test_run_failure_still_writes_error_runtime_log(sheets, fake_config, prompts_dir, fake_spreadsheet):
    claude = StubClaudeClient(raise_exc=RuntimeError("boom"))
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    with pytest.raises(RuntimeError):
        agent.run()

    rt_rows = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert len(rt_rows) == 1
    assert rt_rows[0]["status"] == "error"
    assert "RuntimeError" in rt_rows[0]["errors"]


def test_parse_response_handles_fenced_json(sheets, fake_config, prompts_dir):
    fenced = "```json\n" + _good_response_json() + "\n```"
    claude = StubClaudeClient(next_text=fenced)
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    memo = agent.run()
    assert memo.summary.startswith("Cold prospecting")


def test_recommendation_round_trip():
    d = {
        "priority": 1,
        "action": "X",
        "why": "because",
        "impact_dollars_per_week": 42.0,
        "confidence": "high",
        "effort": "low",
        "depends_on": ["dep"],
    }
    r = Recommendation.from_dict(d)
    assert r.to_dict() == d


def test_dry_run_skips_sheet_writes_and_prints(sheets, fake_config, prompts_dir, fake_spreadsheet, capsys):
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir, dry_run=True)
    memo = agent.run()
    assert memo.agent == "AdsAgent"

    # No rows written to either tab.
    assert fake_spreadsheet.worksheet("Agent Memos").get_all_records() == []
    assert fake_spreadsheet.worksheet("Runtime Log").get_all_records() == []

    # Memo printed to stdout.
    out = capsys.readouterr().out
    assert "[DRY RUN] AdsAgent" in out
    assert "Cold prospecting healthy" in out
    assert "[DRY RUN] AdsAgent runtime:" in out


def test_dry_run_defaults_from_config(sheets, fake_config, prompts_dir, fake_spreadsheet):
    # Build a config with dry_run=True (frozen dataclass — replace).
    from dataclasses import replace as dc_replace

    cfg = dc_replace(fake_config, dry_run=True)
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, cfg, prompts_dir=prompts_dir)
    assert agent.dry_run is True
    agent.run()
    assert fake_spreadsheet.worksheet("Agent Memos").get_all_records() == []


class _TabAgent(BaseAgent):
    """Real BaseAgent subclass (not the stub) so default gather_data runs."""

    name = "AdsAgent"
    role_prompt_file = "ads.md"


def test_gather_data_caps_rows_per_tab(sheets, fake_config, prompts_dir):
    """Big tabs must be truncated to the last N rows to fit the token budget."""
    sheets.ensure_tab("HugeTab", ["week", "value"])
    for i in range(500):
        sheets.append_row("HugeTab", [f"2024-W{i:03d}", i])

    class HugeAgent(_TabAgent):
        data_tabs = ["HugeTab"]
        max_rows_per_tab = 50

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = HugeAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    data = agent.gather_data()
    payload = data["HugeTab"]
    assert payload["_total_rows"] == 500
    assert payload["_kept_last"] == 50
    assert len(payload["rows"]) == 50
    assert payload["rows"][0]["value"] == 450
    assert payload["rows"][-1]["value"] == 499


def test_gather_data_does_not_wrap_small_tabs(sheets, fake_config, prompts_dir):
    sheets.ensure_tab("SmallTab", ["week", "value"])
    # 3 rows is below the default cap of 4, so the payload should pass
    # through as a raw list (no _total_rows / _kept_last envelope).
    for i in range(3):
        sheets.append_row("SmallTab", [f"2024-W{i:03d}", i])

    class SmallAgent(_TabAgent):
        data_tabs = ["SmallTab"]

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = SmallAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    data = agent.gather_data()
    assert isinstance(data["SmallTab"], list)
    assert len(data["SmallTab"]) == 3


def test_build_prompt_emits_cacheable_system_blocks(sheets, fake_config, prompts_dir):
    """The memory block must carry cache_control so the role+context+baseline
    prefix is cached for the next agent in the run."""
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()

    sys_blocks = claude.last_system
    assert isinstance(sys_blocks, list)
    assert len(sys_blocks) == 4  # role + context + baseline + memory
    # cache_control on the last (memory) block caches everything above it.
    assert sys_blocks[-1].get("cache_control") == {"type": "ephemeral"}
    # role / context / baseline blocks are stable across the weekly run.
    assert sys_blocks[0]["text"]  # role
    assert "BUSINESS CONTEXT" in sys_blocks[1]["text"]
    assert "AGENT BASELINE" in sys_blocks[2]["text"]
    # The volatile per-week data lives in the user message, not system.
    assert "THIS WEEK'S DATA" in claude.last_user_message
    assert "BUSINESS CONTEXT" not in claude.last_user_message


def test_baseline_rows_appear_in_system_block(sheets, fake_config, prompts_dir):
    """Curated baseline sections render as named blocks the agent can read."""
    # Seed the BASELINE: AdsAgent tab. StubAgent.name == "AdsAgent".
    sheets.append_row(
        "BASELINE: AdsAgent",
        [
            "normal_metrics_range",
            "Prospect ASC CPM typically $18-25; CTR 1.4-1.8%.",
            "2026-04-15",
            "high",
        ],
    )
    sheets.append_row(
        "BASELINE: AdsAgent",
        [
            "attribution_caveats",
            "RT-customer ROAS is ~50% WhatsApp-inflated.",
            "2026-04-15",
            "high",
        ],
    )

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()

    baseline_block = claude.last_system[2]["text"]
    assert "[normal_metrics_range]" in baseline_block
    assert "Prospect ASC CPM" in baseline_block
    assert "[attribution_caveats]" in baseline_block
    assert "confidence=high" in baseline_block


def test_empty_baseline_renders_placeholder(sheets, fake_config, prompts_dir):
    """First-run case: no baseline rows yet. The block stays present in the
    system prefix (so the cache key shape is stable) with a clear placeholder."""
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()

    baseline_block = claude.last_system[2]["text"]
    assert "no baseline yet" in baseline_block


def test_preferred_model_is_forwarded_to_client(sheets, fake_config, prompts_dir):
    """ContentAgent / SEOAgent override preferred_model to route to Haiku."""

    class HaikuAgent(StubAgent):
        preferred_model = "claude-haiku-4-5"

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = HaikuAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()
    assert claude.last_model == "claude-haiku-4-5"


def test_preferred_model_defaults_to_none(sheets, fake_config, prompts_dir):
    """Unspecified preferred_model passes None — the client falls back to
    its default model (config.anthropic_model)."""
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()
    assert claude.last_model is None


def test_preferred_max_tokens_is_forwarded_to_client(sheets, fake_config, prompts_dir):
    """GoalsAgent overrides preferred_max_tokens because its action-plan JSON
    is larger than specialists' memos. First production run (2026-05-22) hit
    mid-JSON truncation at the default; this test guards the override path."""

    class BigOutputAgent(StubAgent):
        preferred_max_tokens = 8000

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = BigOutputAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()
    assert claude.last_max_tokens == 8000


def test_preferred_max_tokens_defaults_to_none(sheets, fake_config, prompts_dir):
    """Unspecified preferred_max_tokens passes None — the client falls back
    to its default (currently 2500)."""
    claude = StubClaudeClient(next_text=_good_response_json())
    agent = StubAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    agent.run()
    assert claude.last_max_tokens is None


def test_default_max_rows_per_tab_is_4(sheets, fake_config, prompts_dir):
    """4 weeks is enough for w/w trend detection; the BASELINE tab carries
    the long-run wisdom that 12 weeks of raw data used to approximate."""

    class DefaultCapAgent(_TabAgent):
        data_tabs = ["WeeklyTab"]

    sheets.ensure_tab("WeeklyTab", ["week", "value"])
    for i in range(30):
        sheets.append_row("WeeklyTab", [f"2024-W{i:03d}", i])

    claude = StubClaudeClient(next_text=_good_response_json())
    agent = DefaultCapAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    data = agent.gather_data()
    payload = data["WeeklyTab"]
    assert payload["_kept_last"] == 4
    assert len(payload["rows"]) == 4


def test_subclass_requires_name_and_role_file(sheets, fake_config, prompts_dir):
    class NoName(BaseAgent):
        role_prompt_file = "ads.md"

    class NoRole(BaseAgent):
        name = "X"

    claude = StubClaudeClient()
    with pytest.raises(ValueError):
        NoName(claude, sheets, fake_config, prompts_dir=prompts_dir)
    with pytest.raises(ValueError):
        NoRole(claude, sheets, fake_config, prompts_dir=prompts_dir)
