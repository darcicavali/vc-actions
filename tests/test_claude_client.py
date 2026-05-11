import json

import pytest

from scripts.claude_client import (
    ClaudeClient,
    ClaudeResponse,
    parse_json_response,
    strip_json_fences,
)


def test_real_client_constructs_without_error():
    """Smoke test: real ClaudeClient must construct successfully.

    The agent stubs in other tests never instantiate the real anthropic SDK,
    so dependency incompatibilities (e.g. anthropic 0.39 + httpx >=0.28
    failing with 'unexpected keyword argument: proxies') slip through.
    This test catches those at CI time.
    """
    client = ClaudeClient(api_key="sk-fake-not-used", model="claude-sonnet-4-5-20250929")
    assert client.model == "claude-sonnet-4-5-20250929"


def test_real_client_requires_api_key():
    with pytest.raises(ValueError):
        ClaudeClient(api_key="", model="claude-sonnet-4-5-20250929")


def test_strip_fences_handles_plain_json():
    assert strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_strip_fences_strips_json_fence():
    raw = '```json\n{"a": 1}\n```'
    assert strip_json_fences(raw) == '{"a": 1}'


def test_strip_fences_strips_unlabeled_fence():
    raw = '```\n{"a": 1}\n```'
    assert strip_json_fences(raw) == '{"a": 1}'


def test_parse_json_response_handles_fenced_output():
    parsed = parse_json_response('```json\n{"summary": "hi"}\n```')
    assert parsed == {"summary": "hi"}


def test_parse_json_response_raises_on_bad_json():
    with pytest.raises(ValueError):
        parse_json_response("not json")


def test_cost_calc_uses_known_model_rates():
    resp = ClaudeResponse(
        text="x",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        model="claude-sonnet-4-5-20250929",
    )
    # 3.0 + 15.0 USD per million in/out
    assert resp.cost_usd == pytest.approx(18.0, rel=1e-6)


def test_cost_calc_falls_back_for_unknown_model():
    resp = ClaudeResponse(
        text="x",
        input_tokens=500_000,
        output_tokens=0,
        model="unknown-model",
    )
    # fallback = default = $3/M input
    assert resp.cost_usd == pytest.approx(1.5, rel=1e-6)
