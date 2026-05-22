"""Integration test for AdsAgent.

Wires together: real BaseAgent.run() flow + real ads.md role prompt +
real base_context.md + memory layer (with a lesson) + fake sheets + stub
Claude. Verifies the prompt that Claude WOULD receive contains everything
the spec requires.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents.ads_agent import DATA_TABS, AdsAgent
from scripts.claude_client import ClaudeResponse
from scripts.config import Config
from tests.fixtures.ads_data import (
    META_BY_AD,
    META_BY_AD_SET,
    META_BY_CAMPAIGN,
    META_DEMOGRAPHICS,
    META_SUMMARY,
)


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
            input_tokens=12_000,
            output_tokens=900,
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


def _seed_meta_tabs(sheets, fake_spreadsheet):
    """Materialize Meta Ads tabs with sample data."""
    seeds = {
        "Meta Ads Summary": META_SUMMARY,
        "Meta Ads by Campaign": META_BY_CAMPAIGN,
        "Meta Ads by Ad Set": META_BY_AD_SET,
        "Meta Ads by Ad": META_BY_AD,
        "Meta Ads Demographics": META_DEMOGRAPHICS,
    }
    for tab, rows in seeds.items():
        headers = list(rows[0].keys())
        sheets.ensure_tab(tab, headers)
        for r in rows:
            sheets.append_row(tab, [r[h] for h in headers])


def _good_response() -> str:
    return json.dumps(
        {
            "summary": "Cold prospecting healthy; RT-non-customer showing creative fatigue.",
            "diagnosis": "Prospect ASC CPM $3.07 stable, ATC 4.3% — room to scale. RT-non-customer freq 3.54 with CTR drifting down — classic top-funnel fatigue. RT-customer ROAS 21.5 is WhatsApp-inflated; effective ~10x, still healthy.",
            "recommendations": [
                {
                    "priority": 1,
                    "action": "Refresh RT-non-customer creative (new static or 30s reel)",
                    "why": "Frequency 3.54 with CTR drift = audience-side fatigue.",
                    "impact_dollars_per_week": 150,
                    "confidence": "high",
                    "effort": "medium",
                    "depends_on": [],
                },
                {
                    "priority": 2,
                    "action": "Scale Prospect ASC +$10/day",
                    "why": "Stable CPM, ATC 4.3% — room to fill funnel.",
                    "impact_dollars_per_week": 40,
                    "confidence": "medium",
                    "effort": "low",
                    "depends_on": [],
                },
            ],
            "watch_list": [
                "RT-non-customer CTR post-refresh",
                "Account ATC rate trend",
            ],
            "data_quality": "high",
        }
    )


def test_ads_agent_full_run(sheets, fake_spreadsheet, fake_config, prompts_dir):
    _seed_meta_tabs(sheets, fake_spreadsheet)
    # Plant a lesson so we know the memory layer is wired end-to-end.
    today = datetime.now(timezone.utc).date().isoformat()
    sheets.append_row(
        "Agent Knowledge",
        [today, "ALL", "strategy", "no TikTok ads ever", "TRUE", "", ""],
    )

    claude = StubClaudeClient(next_text=_good_response())
    agent = AdsAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    memo = agent.run()

    # Returned memo is well-formed.
    assert memo.agent == "AdsAgent"
    assert len(memo.recommendations) == 2
    assert memo.recommendations[0].priority == 1
    assert "creative" in memo.recommendations[0].action.lower()

    # The prompt Claude received includes role, business context, lessons,
    # memory placeholders, all 5 data tabs, and the JSON-output instruction.
    p = claude.last_prompt
    assert "Senior Paid Media Strategist" in p
    assert "Vanessa Cavali Boutique" in p
    assert "no TikTok ads ever" in p
    assert "(no prior memos)" in p
    assert "(no recorded outcomes)" in p
    for tab in DATA_TABS:
        assert tab in p
    assert "Prospect ASC" in p
    assert "RT - non customer" in p
    assert "Return ONLY the JSON" in p

    # Memo row persisted.
    rows = fake_spreadsheet.worksheet("Agent Memos").get_all_records()
    assert len(rows) == 1
    assert rows[0]["agent"] == "AdsAgent"
    parsed_recs = json.loads(rows[0]["recommendations_json"])
    assert len(parsed_recs) == 2
    assert parsed_recs[0]["impact_dollars_per_week"] == 150

    # Runtime log row persisted with token + cost data.
    rt = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert len(rt) == 1
    assert rt[0]["status"] == "ok"
    assert rt[0]["input_tokens"] == 12_000
    assert rt[0]["output_tokens"] == 900
    # 12k input * $3/M + 900 output * $15/M = 0.036 + 0.0135 = 0.0495
    assert abs(float(rt[0]["cost_usd"]) - 0.0495) < 1e-6
    assert "Cold prospecting healthy" in rt[0]["key_insight"]


def test_ads_agent_handles_missing_tab_gracefully(sheets, fake_spreadsheet, fake_config, prompts_dir):
    # Only seed some tabs; the rest should surface as errors but the run continues.
    headers = list(META_SUMMARY[0].keys())
    sheets.ensure_tab("Meta Ads Summary", headers)
    for r in META_SUMMARY:
        sheets.append_row("Meta Ads Summary", [r[h] for h in headers])

    claude = StubClaudeClient(next_text=_good_response())
    agent = AdsAgent(claude, sheets, fake_config, prompts_dir=prompts_dir)
    memo = agent.run()
    assert memo.agent == "AdsAgent"
    # Prompt mentions the error placeholder for missing tabs.
    assert "WorksheetNotFound" in claude.last_prompt or "error" in claude.last_prompt
