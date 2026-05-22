"""Parametrized smoke test for every specialist agent.

For each one we verify:
- name + role_prompt_file are set
- the prompt file actually exists
- run() walks the full memory-aware flow and writes a memo + runtime log
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from agents import (
    AdsAgent,
    ContentAgent,
    CustomerAgent,
    FinancialAgent,
    FunnelAgent,
    ProductAgent,
    SEOAgent,
)
from scripts.claude_client import ClaudeResponse
from scripts.config import Config


ALL_SPECIALISTS = [
    AdsAgent,
    CustomerAgent,
    ProductAgent,
    ContentAgent,
    FunnelAgent,
    FinancialAgent,
    SEOAgent,
]


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
            input_tokens=8_000,
            output_tokens=500,
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


def _generic_response() -> str:
    return json.dumps(
        {
            "summary": "Test summary.",
            "diagnosis": "Test diagnosis text.",
            "recommendations": [
                {
                    "priority": 1,
                    "action": "Do the thing",
                    "why": "Because data.",
                    "impact_dollars_per_week": 100,
                    "confidence": "medium",
                    "effort": "low",
                    "depends_on": [],
                }
            ],
            "watch_list": ["something"],
            "data_quality": "medium",
        }
    )


@pytest.mark.parametrize("agent_cls", ALL_SPECIALISTS)
def test_specialist_metadata(agent_cls, prompts_dir):
    assert agent_cls.name, f"{agent_cls.__name__} missing name"
    assert agent_cls.role_prompt_file, f"{agent_cls.__name__} missing role_prompt_file"
    role_path = prompts_dir / agent_cls.role_prompt_file
    assert role_path.exists(), f"Role prompt {role_path} not found"
    assert agent_cls.data_tabs, f"{agent_cls.__name__} should declare data_tabs"


@pytest.mark.parametrize("agent_cls", ALL_SPECIALISTS)
def test_specialist_run_writes_memo(agent_cls, sheets, fake_spreadsheet, fake_config, prompts_dir):
    claude = StubClaudeClient(next_text=_generic_response())
    agent = agent_cls(claude, sheets, fake_config, prompts_dir=prompts_dir)
    memo = agent.run()
    assert memo.agent == agent_cls.name
    rows = fake_spreadsheet.worksheet("Agent Memos").get_all_records()
    assert any(r["agent"] == agent_cls.name for r in rows)
    rt = fake_spreadsheet.worksheet("Runtime Log").get_all_records()
    assert any(r["agent"] == agent_cls.name and r["status"] == "ok" for r in rt)
    # Every declared tab name should appear in the prompt (as the JSON key).
    for tab in agent_cls.data_tabs:
        assert tab in claude.last_prompt
