"""Conversational chat layer over the multiagent system.

Two transports share one brain:
- chat.web_app    — Streamlit UI at localhost:8501
- chat.telegram_app — Telegram long-polling bot

Both call into chat.brain.handle_message(...) which holds the conversation
loop, tool dispatch, prompt caching, and confirmation guardrails.
"""
