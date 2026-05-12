"""Telegram bot transport.

Run:
    python -m chat.telegram_app

Required env vars (in addition to ANTHROPIC_API_KEY / GOOGLE_*):
- TELEGRAM_BOT_TOKEN          — from @BotFather
- TELEGRAM_ALLOWED_USER_ID    — Darci's Telegram user id (integer).
                                Bot ignores messages from anyone else.
                                Find via @userinfobot.

The bot uses long-polling, so no public URL is required — runs from
your laptop, a Raspberry Pi, or a small cloud container. Sleep your
laptop and Telegram queues messages; bot delivers when it wakes.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anthropic  # noqa: E402

# python-telegram-bot is an optional dependency — only imported when the
# Telegram transport actually runs. Tests don't import this module.
from telegram import Update  # noqa: E402
from telegram.constants import ChatAction  # noqa: E402
from telegram.ext import (  # noqa: E402
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from chat.brain import (  # noqa: E402
    ChatBrain,
    TextDelta,
    ToolCallEnded,
    ToolCallStarted,
    TurnEnded,
)
from chat.memory import ConversationStore  # noqa: E402
from scripts.config import load_config  # noqa: E402
from scripts.sheets_client import SheetsClient  # noqa: E402


CONVERSATION_ID = "darci"
TELEGRAM_MAX_CHARS = 4000  # API limit is 4096; keep buffer for footer

LOG = logging.getLogger("chat.telegram")


def _allowed_user_id() -> int:
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not raw:
        raise RuntimeError(
            "TELEGRAM_ALLOWED_USER_ID env var must be set (find via @userinfobot)"
        )
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(f"TELEGRAM_ALLOWED_USER_ID must be an integer: {raw}") from e


def _is_authorized(update: Update, allowed_user_id: int) -> bool:
    user = update.effective_user
    return user is not None and user.id == allowed_user_id


def _split_for_telegram(text: str) -> list[str]:
    """Split a long reply into Telegram-sized chunks at paragraph
    boundaries when possible, falling back to character cuts."""
    if len(text) <= TELEGRAM_MAX_CHARS:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > TELEGRAM_MAX_CHARS:
        cut = remaining.rfind("\n\n", 0, TELEGRAM_MAX_CHARS)
        if cut == -1:
            cut = remaining.rfind("\n", 0, TELEGRAM_MAX_CHARS)
        if cut == -1:
            cut = TELEGRAM_MAX_CHARS
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.bot_data["allowed_user_id"]):
        LOG.warning("ignored message from unauthorized user %s", update.effective_user)
        return
    if update.message is None or not update.message.text:
        return

    user_text = update.message.text
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Construct the brain per-turn. Cheap (no network), and avoids
    # cross-turn state on a long-lived process.
    brain = ChatBrain(
        context.bot_data["anthropic_client"],
        context.bot_data["sheets"],
        context.bot_data["store"],
        transport="telegram",
        conversation_id=CONVERSATION_ID,
    )

    text_buf: list[str] = []
    tools_used: list[str] = []
    footer = ""

    try:
        for event in brain.handle_message(user_text):
            if isinstance(event, TextDelta):
                text_buf.append(event.text)
            elif isinstance(event, ToolCallStarted):
                tools_used.append(event.name)
            elif isinstance(event, ToolCallEnded):
                pass  # tool_used already recorded; result included via the model's text turn
            elif isinstance(event, TurnEnded):
                if event.stopped_early_reason:
                    footer = f"\n\n_(stopped: {event.stopped_early_reason})_"
    except Exception as e:  # noqa: BLE001
        LOG.exception("chat turn failed")
        await update.message.reply_text(
            f"Sorry, the bot hit an error and stopped: {e}\n\n"
            f"Try again, or check the logs."
        )
        return

    body = "".join(text_buf).strip()
    if tools_used:
        body += f"\n\n_used: {', '.join(tools_used)}_"
    body += footer
    if not body:
        body = "_(no text response — check the logs)_"

    for chunk in _split_for_telegram(body):
        await update.message.reply_text(chunk, parse_mode=None)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    await update.message.reply_text(
        "Operator chat is online. Ask anything about your business — "
        "I have access to the spreadsheet, the agent baselines, and "
        "the weekly memos. /reset clears our conversation history."
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.bot_data["allowed_user_id"]):
        return
    n = context.bot_data["store"].reset(CONVERSATION_ID)
    await update.message.reply_text(f"Cleared {n} messages from history.")


def build_application() -> Application:
    """Wire up the bot. Separated from main() so tests can introspect it."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")

    config = load_config()
    anthropic_client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    sheets = SheetsClient.from_config(config)
    store = ConversationStore()
    sheets.ensure_all_tabs()  # makes sure Bot Actions / Bot Notes exist

    app = Application.builder().token(token).build()
    app.bot_data.update(
        {
            "anthropic_client": anthropic_client,
            "sheets": sheets,
            "store": store,
            "allowed_user_id": _allowed_user_id(),
        }
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


def main() -> None:
    app = build_application()
    LOG.info("Telegram bot starting (long-polling). Ctrl-C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
