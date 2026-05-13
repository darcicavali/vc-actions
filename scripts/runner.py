"""Weekly run orchestrator.

Phase 1: run all 7 specialists (one fail does not block the others).
Phase 2: run the coordinator (GoalsAgent), which reads what landed.
Phase 3: send the digest email via Omnisend (skipped in dry-run mode).

Honors `VC_ACTIONS_DRY_RUN=true` — agents print memos instead of writing
to the sheet, and the digest email is skipped.

Usage:
    python -m scripts.runner               # live run
    VC_ACTIONS_DRY_RUN=true python -m scripts.runner    # safe preview
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from typing import Iterable

from agents import (
    AdsAgent,
    BaseAgent,
    ContentAgent,
    CustomerAgent,
    FinancialAgent,
    FunnelAgent,
    GoalsAgent,
    ProductAgent,
    SEOAgent,
)
from scripts.claude_client import ClaudeClient
from scripts.config import Config, get_config
from scripts.omnisend_client import OmnisendClient
from scripts.sheets_client import SheetsClient


SPECIALIST_CLASSES: list[type[BaseAgent]] = [
    AdsAgent,
    CustomerAgent,
    ProductAgent,
    ContentAgent,
    FunnelAgent,
    FinancialAgent,
    SEOAgent,
]

# Pause between specialist runs to stay under Claude's per-minute token rate
# limit (default tier: 30k input tokens/minute). Overridable via env var so
# users on higher tiers can shorten or skip the pause.
DEFAULT_INTER_AGENT_DELAY_SECONDS = 60


def _inter_agent_delay() -> int:
    raw = os.environ.get("VC_ACTIONS_INTER_AGENT_DELAY_SECONDS")
    if raw is None:
        return DEFAULT_INTER_AGENT_DELAY_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_INTER_AGENT_DELAY_SECONDS


def _build_clients(config: Config) -> tuple[ClaudeClient, SheetsClient]:
    claude = ClaudeClient(api_key=config.anthropic_api_key, model=config.anthropic_model)
    sheets = SheetsClient.from_config(config)
    return claude, sheets


def _run_specialists(
    config: Config, claude: ClaudeClient, sheets: SheetsClient, dry_run: bool
) -> dict[str, str]:
    """Returns {agent_name: status} ('ok' or short error string)."""
    statuses: dict[str, str] = {}
    delay = _inter_agent_delay()
    for i, cls in enumerate(SPECIALIST_CLASSES):
        agent = cls(claude, sheets, config, dry_run=dry_run)
        print(f"[{agent.name}] running...")
        try:
            memo = agent.run()
            statuses[agent.name] = "ok"
            print(f"[{agent.name}] {len(memo.recommendations)} recs")
        except Exception as e:
            statuses[agent.name] = f"{type(e).__name__}: {e}"
            print(f"[{agent.name}] FAILED: {statuses[agent.name]}")
            print(traceback.format_exc())
        # Sleep between agents to stay under rate limits. Skip after the last
        # specialist (the coordinator follows but uses memo data, not raw
        # sheet dumps, so its prompt is much smaller).
        if delay and i < len(SPECIALIST_CLASSES) - 1:
            print(f"[runner] sleeping {delay}s before next agent...")
            time.sleep(delay)
    return statuses


def _run_coordinator(
    config: Config, claude: ClaudeClient, sheets: SheetsClient, dry_run: bool
) -> GoalsAgent | None:
    coordinator = GoalsAgent(claude, sheets, config, dry_run=dry_run)
    print(f"[{coordinator.name}] running...")
    try:
        coordinator.run()
        print(f"[{coordinator.name}] ok")
        return coordinator
    except Exception as e:
        print(f"[{coordinator.name}] FAILED: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return None


def _send_digest_email(config: Config, coordinator: GoalsAgent) -> None:
    plan = coordinator.last_plan
    if plan is None:
        print("[digest] no plan to send")
        return
    if not config.omnisend_api_key or not config.omnisend_digest_recipient:
        print("[digest] Omnisend not configured — skipping email")
        return
    client = OmnisendClient(api_key=config.omnisend_api_key)
    result = client.trigger_event(
        event_name=config.omnisend_digest_event,
        recipient_email=config.omnisend_digest_recipient,
        properties={
            "summary": plan.summary,
            "one_thing_this_week": plan.one_thing_this_week,
            "email_body": plan.summary_email_body,
            "generated_at": plan.generated_at,
        },
    )
    print(f"[digest] omnisend status={result.status_code}")


def run_weekly(*, dry_run: bool | None = None, bootstrap_only: bool = False) -> int:
    config = get_config()
    effective_dry_run = config.dry_run if dry_run is None else dry_run

    print(
        f"[runner] starting weekly run "
        f"(dry_run={effective_dry_run}, bootstrap_only={bootstrap_only})"
    )

    # Dry-run still needs sheets to READ data; bootstrap-only only writes
    # the tab schema. Either way we need a real sheets connection.
    claude, sheets = _build_clients(config)

    # Tab creation is idempotent and schema-only — safe to run in any mode.
    # Doing it always (not just on real runs) lets dry-run and bootstrap-only
    # validate the schema without paying for an agent pass.
    try:
        sheets.ensure_all_tabs()
    except Exception as e:
        print(f"[runner] ensure_all_tabs failed: {e}")

    if bootstrap_only:
        print("[runner] bootstrap_only=true — tabs ensured, exiting without agent runs")
        return 0

    statuses = _run_specialists(config, claude, sheets, dry_run=effective_dry_run)

    coordinator = _run_coordinator(config, claude, sheets, dry_run=effective_dry_run)
    if coordinator and coordinator.last_plan and not effective_dry_run:
        _send_digest_email(config, coordinator)

    failures = [name for name, status in statuses.items() if status != "ok"]
    print(f"[runner] done. specialist failures: {failures or 'none'}")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="vc-actions weekly run")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print memos instead of writing to the sheet; skip the digest email.",
    )
    parser.add_argument(
        "--bootstrap-only",
        action="store_true",
        help="Create any missing sheet tabs and exit. No Claude calls, costs $0.",
    )
    args = parser.parse_args(argv)
    dry_run_override = True if args.dry_run else None
    return run_weekly(dry_run=dry_run_override, bootstrap_only=args.bootstrap_only)


if __name__ == "__main__":
    sys.exit(main())
