"""Tests for ResendClient.

Mock the requests.post call — we never hit the network.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from scripts.resend_client import ResendClient, ResendResult


def test_requires_api_key():
    with pytest.raises(ValueError):
        ResendClient(api_key="")


def test_send_email_posts_expected_payload():
    client = ResendClient(api_key="test_key")
    fake_response = MagicMock(status_code=200, text='{"id":"abc"}')
    with patch("scripts.resend_client.requests.post", return_value=fake_response) as mock_post:
        result = client.send_email(
            sender="VC Actions <onboarding@resend.dev>",
            recipient="darci@example.com",
            subject="VC Weekly Plan — 2026-05-22",
            text="hello",
        )
    assert isinstance(result, ResendResult)
    assert result.status_code == 200
    assert result.body == '{"id":"abc"}'

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.resend.com/emails"
    body = kwargs["json"]
    assert body["from"] == "VC Actions <onboarding@resend.dev>"
    assert body["to"] == ["darci@example.com"]
    assert body["subject"] == "VC Weekly Plan — 2026-05-22"
    assert body["text"] == "hello"
    assert "html" not in body
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer test_key"
    assert headers["Content-Type"] == "application/json"


def test_send_email_includes_html_when_provided():
    client = ResendClient(api_key="test_key")
    fake_response = MagicMock(status_code=200, text="{}")
    with patch("scripts.resend_client.requests.post", return_value=fake_response) as mock_post:
        client.send_email(
            sender="from@x.com",
            recipient="to@x.com",
            subject="s",
            text="t",
            html="<p>t</p>",
        )
    body = mock_post.call_args[1]["json"]
    assert body["html"] == "<p>t</p>"
