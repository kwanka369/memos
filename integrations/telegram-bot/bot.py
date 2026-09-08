#!/usr/bin/env python3
"""
Telegram -> Memos inbox bridge.

Polls a Telegram bot for new messages and creates a Memos entry for each one.
Messages can start with a prefix to route them into a specific tag:

    !link     -> #link
    !music    -> #music
    !idea     -> #idea
    !meeting  -> #meeting
    !podcast  -> #podcast
    !todo     -> #todo

Anything without a recognized prefix is filed under #inbox.

Photos, documents, voice notes, audio, and video notes are downloaded from
Telegram and attached to the created memo via the Memos attachments API.

YouTube links are enriched with the video title and channel name (via the
public oEmbed API) prepended to the memo content.

Run:
    pip install -r requirements.txt
    python3 bot.py
"""
import base64
import mimetypes
import os
import re
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
    "!music": "music",
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


YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+|"
    r"youtube\.com/shorts/[\w-]+)\S*"
)


def get_youtube_oembed(url: str) -> dict | None:
    """Fetch title/author/thumbnail for a YouTube URL via the public oEmbed API."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def enrich_with_youtube_metadata(content: str) -> str:
    match = YOUTUBE_URL_RE.search(content)
    if not match:
        return content
    info = get_youtube_oembed(match.group(0))
    if not info:
        return content
    title = info.get("title", "")
    author = info.get("author_name", "")
    if not title:
        return content
    header = f"🎵 {title} — {author}" if author else f"🎵 {title}"
    return f"{header}\n{content}"


def create_memo(content: str) -> str:
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
    return resp.json()["name"]  # e.g. "memos/abc123"


def download_telegram_file(file_id: str) -> tuple[bytes, str]:
    """Returns (file_bytes, file_path) for a Telegram file_id."""
    resp = requests.get(
        f"{TELEGRAM_API}/getFile", params={"file_id": file_id}, timeout=10
    )
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    file_resp = requests.get(file_url, timeout=30)
    file_resp.raise_for_status()
    return file_resp.content, file_path


def attach_file_to_memo(memo_name: str, filename: str, mime_type: str, data: bytes) -> None:
    resp = requests.post(
        f"{MEMOS_URL}/api/v1/attachments",
        headers={
            "Authorization": f"Bearer {MEMOS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "filename": filename,
            "type": mime_type or "application/octet-stream",
            "content": base64.b64encode(data).decode("ascii"),
            "memo": memo_name,
        },
        timeout=30,
    )
    resp.raise_for_status()


# Telegram update fields that carry a file, in priority order (largest/most
# specific first), and how to derive a filename from them.
FILE_FIELDS = ("document", "video", "voice", "audio", "video_note")


def extract_file(message: dict) -> tuple[str, str, str] | None:
    """Returns (file_id, filename, mime_type) for the first file found, or None."""
    if "photo" in message:
        # photo is a list of sizes; take the largest (last one)
        largest = message["photo"][-1]
        return largest["file_id"], f"{largest['file_id']}.jpg", "image/jpeg"

    for field in FILE_FIELDS:
        if field in message:
            item = message[field]
            file_id = item["file_id"]
            mime_type = item.get("mime_type", "")
            filename = item.get("file_name")
            if not filename:
                ext = mimetypes.guess_extension(mime_type) or ""
                filename = f"{field}_{file_id}{ext}"
            return file_id, filename, mime_type
    return None


def handle_update(update: dict) -> None:
    message = update.get("message")
    if not message:
        return

    text = message.get("text") or message.get("caption") or ""
    content = build_memo_content(text) if text else "#inbox (file)"
    content = enrich_with_youtube_metadata(content)
    memo_name = create_memo(content)
    print(f"Saved memo: {content!r}")

    file_info = extract_file(message)
    if file_info:
        file_id, filename, mime_type = file_info
        data, _ = download_telegram_file(file_id)
        attach_file_to_memo(memo_name, filename, mime_type, data)
        print(f"Attached file {filename!r} ({len(data)} bytes) to {memo_name}")


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
