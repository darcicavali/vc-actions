"""Omnisend client for the weekly digest email.

Single use case: trigger a custom event for a contact. Omnisend automation
listens on that event and renders the email from the event payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


OMNISEND_BASE_URL = "https://api.omnisend.com/v3"


@dataclass
class OmnisendResult:
    status_code: int
    body: str


class OmnisendClient:
    def __init__(self, api_key: str, base_url: str = OMNISEND_BASE_URL):
        if not api_key:
            raise ValueError("OMNISEND_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def trigger_event(
        self, *, event_name: str, recipient_email: str, properties: dict[str, Any]
    ) -> OmnisendResult:
        url = f"{self.base_url}/events"
        payload = {
            "eventName": event_name,
            "email": recipient_email,
            "fields": properties,
        }
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return OmnisendResult(status_code=resp.status_code, body=resp.text)
