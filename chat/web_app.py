"""Streamlit chat UI for the bot.

Run:
    streamlit run chat/web_app.py

Loads ANTHROPIC_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON
from the environment (same as the weekly runner). Conversation history
persists to chat/data/conversations.db so refreshing or restarting
preserves context.

Streamlit reruns this entire script on every user interaction. We cache
the heavy clients (Anthropic, SheetsClient, ConversationStore) in
`st.session_state` so subsequent reruns stay fast.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running via `streamlit run chat/web_app.py` from the repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anthropic  # noqa: E402
import streamlit as st  # noqa: E402

from chat.brain import (  # noqa: E402
    ChatBrain,
    TextDelta,
    ToolCallEnded,
    ToolCallStarted,
    TurnEnded,
)
from chat.memory import ConversationStore  # noqa: E402
from scripts.config import get_config  # noqa: E402
from scripts.sheets_client import SheetsClient  # noqa: E402


CONVERSATION_ID = "darci"


def _get_clients():
    """Construct Anthropic + SheetsClient + ConversationStore once per
    Streamlit session and cache in session_state.
    """
    if "clients" in st.session_state:
        return st.session_state["clients"]
    config = get_config()
    anthropic_client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    sheets = SheetsClient.from_config(config)
    store = ConversationStore()
    st.session_state["clients"] = (anthropic_client, sheets, store)
    return st.session_state["clients"]


def _render_history(store: ConversationStore) -> None:
    """Render persisted conversation. Skips tool_use / tool_result
    blocks — the user only wants to see human-readable text.
    """
    for msg in store.load_recent(CONVERSATION_ID, limit=200):
        role = msg["role"]
        content = msg["content"]
        text = _extract_visible_text(content)
        if not text:
            continue
        with st.chat_message(role):
            st.markdown(text)


def _extract_visible_text(content) -> str:
    """Pull just the human-readable text out of a stored message."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def _stream_assistant_reply(brain: ChatBrain, user_text: str, placeholder) -> None:
    """Run one turn and update the placeholder progressively as text +
    tool events arrive.
    """
    text_buf: list[str] = []
    tool_lines: list[str] = []

    def render():
        body = "".join(text_buf)
        if tool_lines:
            body += "\n\n---\n_" + " · ".join(tool_lines) + "_"
        placeholder.markdown(body or "_thinking…_")

    for event in brain.handle_message(user_text):
        if isinstance(event, TextDelta):
            text_buf.append(event.text)
            render()
        elif isinstance(event, ToolCallStarted):
            tool_lines.append(f"→ {event.name}")
            render()
        elif isinstance(event, ToolCallEnded):
            label = "✗" if event.is_error else "✓"
            # Replace the matching "→ name" entry with the resolved one.
            for i, line in enumerate(tool_lines):
                if line == f"→ {event.name}":
                    tool_lines[i] = f"{label} {event.name}"
                    break
            render()
        elif isinstance(event, TurnEnded):
            footer = (
                f"· {event.iterations} iter · "
                f"in={event.input_tokens}, out={event.output_tokens}, "
                f"cache_read={event.cache_read_tokens} · "
                f"${event.cost_usd:.4f}"
            )
            if event.stopped_early_reason:
                footer += f" · {event.stopped_early_reason}"
            placeholder.markdown("".join(text_buf) + f"\n\n_{footer}_")


def main() -> None:
    st.set_page_config(page_title="VC Actions chat", page_icon=None, layout="centered")
    st.title("Vanessa Cavali — operator chat")
    st.caption(
        "Conversational interface to the multiagent system. Persistent "
        "memory across sessions. Same brain as the Telegram bot."
    )

    anthropic_client, sheets, store = _get_clients()

    # Sidebar controls
    with st.sidebar:
        st.markdown("### Session")
        if st.button("Reset conversation", use_container_width=True):
            n = store.reset(CONVERSATION_ID)
            st.success(f"Cleared {n} messages.")
            st.rerun()
        st.markdown("---")
        st.caption(
            "Conversation persists in `chat/data/conversations.db`. "
            "Reset clears it permanently."
        )

    _render_history(store)

    if user_text := st.chat_input("Ask anything…"):
        with st.chat_message("user"):
            st.markdown(user_text)
        with st.chat_message("assistant"):
            placeholder = st.empty()
            brain = ChatBrain(
                anthropic_client,
                sheets,
                store,
                transport="streamlit",
                conversation_id=CONVERSATION_ID,
            )
            _stream_assistant_reply(brain, user_text, placeholder)


if __name__ == "__main__":
    main()
