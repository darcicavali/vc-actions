# Chat — operator interface to the multiagent system

Two transports, one brain. Talk to the bot on your phone (Telegram) or your laptop (Streamlit) — same conversation history, same tools, same memory.

## Quick start (laptop / Streamlit)

```bash
pip install -r requirements.txt   # picks up streamlit + python-telegram-bot
export ANTHROPIC_API_KEY=...
export GOOGLE_SHEET_ID=...
export GOOGLE_SERVICE_ACCOUNT_JSON='{...}'   # the same JSON the weekly run uses
streamlit run chat/web_app.py
```

Opens at `http://localhost:8501`. Chat persists in `chat/data/conversations.db`.

## Quick start (Telegram)

1. Open Telegram, message `@BotFather`, run `/newbot`. Save the token it gives you.
2. Message `@userinfobot` to get your numeric Telegram user id.
3. Set the env vars:

   ```bash
   export TELEGRAM_BOT_TOKEN=...
   export TELEGRAM_ALLOWED_USER_ID=...
   # plus the ANTHROPIC_API_KEY / GOOGLE_* vars from above
   ```

4. Run the bot:

   ```bash
   python -m chat.telegram_app
   ```

   Long-polling — no public URL needed. Bot only responds to your user id; everyone else is silently ignored.

## What the bot can do

| Tool                  | Purpose                                                    |
|-----------------------|------------------------------------------------------------|
| `read_sheet_tab`      | Read any tab from the workspace                            |
| `read_baseline`       | Pull a specialist agent's curated baseline                 |
| `read_recent_memos`   | Pull recent weekly memos for one agent                     |
| `read_action_plan`    | Pull this week's plan                                      |
| `read_outcomes`       | Pull past recommendation outcomes                          |
| `add_lesson`          | Append a hard rule for future weekly runs (append-only)    |
| `note_for_next_run`   | Append a heads-up the next weekly run will see (append-only) |

Read tools execute immediately. Append-only writes execute immediately and log to the `Bot Actions` audit tab. (Destructive tools — overwrites, deletes — are gated by `chat/guardrails.py`. There are none today; future ones will require explicit "yes" confirmation.)

## Architecture

```
chat/
├── brain.py        # Anthropic loop, prompt caching, tool dispatch, streaming
├── tools.py        # Tool schemas + dispatchers
├── memory.py       # SQLite conversation log
├── audit.py        # Bot Actions tab writes
├── guardrails.py   # Confirmation gate for destructive tools
├── prompts/
│   └── system.md   # Bot persona and behavior rules
├── web_app.py      # Streamlit transport
└── telegram_app.py # Telegram long-polling transport
```

The brain is `chat.brain.ChatBrain.handle_message(text) -> Iterator[ChatEvent]`. Both transports consume the same generator. To add a new transport (Slack, CLI, web API), implement an event consumer — no brain changes needed.

## Cost

Per user message: ~$0.01–0.02 with prompt caching (Opus 4.7, ~5K cached system, ~500-token reply). Even heavy daily use lands under $5/month.

The first message after any change to `prompts/system.md` writes the cache fresh (~$0.025). Every subsequent message reads it at 0.1× rate.

## Deployment (later)

The bot runs fine on your laptop while you're using it. When you're ready to make it always-on:

- **Fly.io** (free tier): `fly launch` from this repo. The included `fly.toml` sets it up with a long-polling Telegram process.
- **Railway** (~$5/mo): connect to GitHub, it auto-deploys on push.
- **Raspberry Pi**: `python -m chat.telegram_app` under `systemd`, runs forever.

Your laptop stays a fine option indefinitely if you don't need 24/7 coverage. Telegram queues messages while the bot is offline and delivers them when it wakes.
