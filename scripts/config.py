"""Configuration loader. Reads env vars + provides typed access.

Convention: env vars are loaded once at process start. `get_config()` is a
small cached factory so tests can monkeypatch env then call again with
`get_config.cache_clear()`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    anthropic_model: str
    google_sheet_id: str
    google_service_account_json: str
    ga4_credentials_json: str
    ga4_property_id: str
    shopify_store_domain: str
    shopify_access_token: str
    omnisend_api_key: str
    omnisend_digest_event: str
    omnisend_digest_recipient: str
    resend_api_key: str
    resend_from: str
    resend_to: str
    test_mode: bool
    dry_run: bool

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    @property
    def prompts_dir(self) -> Path:
        return PROMPTS_DIR


def _b(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        google_sheet_id=os.environ.get("GOOGLE_SHEET_ID", ""),
        google_service_account_json=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""),
        ga4_credentials_json=os.environ.get("GA4_CREDENTIALS_JSON", ""),
        ga4_property_id=os.environ.get("GA4_PROPERTY_ID", ""),
        shopify_store_domain=os.environ.get("SHOPIFY_STORE_DOMAIN", ""),
        shopify_access_token=os.environ.get("SHOPIFY_ACCESS_TOKEN", ""),
        omnisend_api_key=os.environ.get("OMNISEND_API_KEY", ""),
        omnisend_digest_event=os.environ.get("OMNISEND_DIGEST_EVENT", "vc_weekly_plan"),
        omnisend_digest_recipient=os.environ.get("OMNISEND_DIGEST_RECIPIENT", ""),
        resend_api_key=os.environ.get("RESEND_API_KEY", ""),
        resend_from=os.environ.get("RESEND_FROM", "VC Actions <onboarding@resend.dev>"),
        resend_to=os.environ.get("RESEND_TO", ""),
        test_mode=_b("VC_ACTIONS_TEST_MODE", False),
        dry_run=_b("VC_ACTIONS_DRY_RUN", False),
    )
