# Telegram -> Memos Inbox Bridge

A small bridge that turns a Telegram chat into a universal inbox for
[Memos](https://usememos.com). Send yourself a message on Telegram (from
any device) and it becomes a searchable, taggable memo.

## How it works

The script long-polls the Telegram Bot API for new messages and creates a
memo via the Memos REST API (`POST /api/v1/memos`) for each one.

## Tagging convention

Start a message with one of these prefixes to route it to a tag. Otherwise
it falls back to `#inbox`.

| Prefix      | Tag         |
|-------------|-------------|
| `!link`     | `#link`     |
| `!idea`     | `#idea`     |
| `!meeting`  | `#meeting`  |
| `!podcast`  | `#podcast`  |
| `!todo`     | `#todo`     |
| *(none)*    | `#inbox`    |

Example: sending `!link https://example.com cool article` creates a memo
with content `#link https://example.com cool article`.

## Setup

1. Copy `.env.example` to `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `MEMOS_URL` — your Memos instance URL (default `http://localhost:5230`)
   - `MEMOS_TOKEN` — a Personal Access Token from Memos
     (Settings → My Account → Access Tokens)

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run:
   ```bash
   python3 bot.py
   ```

The script keeps track of the last processed Telegram update in
`offset.txt` so it won't reprocess messages after a restart.

## Limitations / next steps

- Only text messages are handled for now. Photos, voice notes, and files
  are ignored (a natural next step: download them and upload via
  `POST /api/v1/resources`, attaching to the created memo).
- No retry/backoff beyond a simple 5s sleep on network errors.
- Intended to run as a single long-lived process (e.g. via `systemd`,
  `docker`, or a simple `nohup`/`screen` session), not as a one-shot script.
