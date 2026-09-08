#!/usr/bin/env python3
"""
Telegram -> Memos inbox bridge.

Polls a Telegram bot for new messages and creates a Memos entry for each one.
Messages can start with a prefix to route them into a specific tag:

    !link     -> #link
    !idea     -> #idea
    !meeting  -> #meeting
    !podcast  -> #podcast
    !todo     -> #todo

Anything without a recognized prefix is filed under #inbox.

Run:
    pip install -r requirements.txt
    python3 bot.py
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MEMOS_URL = os.environ.get("MEMOS_URL", "http://localhost:5230").rstrip("/")
MEMOS_TOKEN = os.environ["MEMOS_TOKEN"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OFFSET_FILE = os.path.join(os.path.dirname(__file__), "offset.txt")

# prefix -> tag mapping
PREFIX_TAGS = {
    "!link": "link",
    "!idea": "idea",
    "!meeting": "meeting",
    "!podcast": "podcast",
    "!todo": "todo",
}


def load_offset() -> int:
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return int(f.read().strip() or 0)
    return 0


def save_offset(offset: int) -> None:
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def build_memo_content(text: str) -> str:
    stripped = text.strip()
    for prefix, tag in PREFIX_TAGS.items():
        if stripped.lower().startswith(prefix):
            rest = stripped[len(prefix):].strip()
            return f"#{tag} {rest}".strip()
    return f"#inbox {stripped}".strip()


def create_memo(content: str) -> None:
    resp = requests.post(
        f"{MEMOS_URL}/api/v1/memos",
        headers={
            "Authorization": f"Bearer {MEMOS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"content": content, "visibility": "PRIVATE"},
        timeout=10,
    )
    resp.raise_for_status()


def handle_update(update: dict) -> None:
    message = update.get("message")
    if not message:
        return
    text = message.get("text")
    if not text:
        # non-text messages (photos, files, voice, ...) are not handled yet
        return
    content = build_memo_content(text)
    create_memo(content)
    print(f"Saved memo: {content!r}")


def main() -> None:
    offset = load_offset()
    print("Telegram -> Memos bridge started. Waiting for messages...")
    while True:
        try:
            resp = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            resp.raise_for_status()
            result = resp.json().get("result", [])
            for update in result:
                handle_update(update)
                offset = update["update_id"] + 1
                save_offset(offset)
        except requests.RequestException as exc:
            print(f"Error polling Telegram: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
