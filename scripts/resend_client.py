"""Resend client for the weekly digest email.

Single use case: send one plain-text email per Monday run with the action
plan to Darci. Resend's free tier (3,000/mo) is plenty for this.

Mirrors the existing OmnisendClient shape so the runner can choose at
call time without conditional plumbing leaking everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


RESEND_BASE_URL = "https://api.resend.com"


@dataclass
class ResendResult:
    status_code: int
    body: str


class ResendClient:
    def __init__(self, api_key: str, base_url: str = RESEND_BASE_URL):
        if not api_key:
            raise ValueError("RESEND_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def send_email(
        self,
        *,
        sender: str,
        recipient: str,
        subject: str,
        text: str,
        html: str | None = None,
    ) -> ResendResult:
        """POST /emails. `sender` must be on a verified domain (or use the
        shared onboarding@resend.dev for low-volume single-recipient sends).
        """
        url = f"{self.base_url}/emails"
        payload: dict[str, Any] = {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": text,
        }
        if html is not None:
            payload["html"] = html
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return ResendResult(status_code=resp.status_code, body=resp.text)
