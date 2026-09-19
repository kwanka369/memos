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
    !github   -> #github
    !task     -> #task (as a Markdown checkbox list)

Anything without a recognized prefix is filed under #inbox.

A voice/audio message captioned "!txt" is transcribed via Gemini and the
transcript is appended to the memo, alongside the original audio attachment.

Photos, documents, voice notes, audio, and video notes are downloaded from
Telegram and attached to the created memo via the Memos attachments API.

YouTube links are enriched with the video title and channel name (via the
public oEmbed API), GitHub repo links are enriched with the repo
description, primary language, and star count (via the public GitHub API),
and Twitter/X status URLs are enriched with the author and tweet text (via
the public fxtwitter API), all prepended to the memo content.

Replying (in Telegram) to a message that was already turned into a memo
creates a Memos *comment* on that memo instead of a new top-level memo.

Run:
    pip install -r requirements.txt
    python3 bot.py
"""
import base64
import json
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_TRANSCRIBE_MODEL = os.environ.get("GEMINI_TRANSCRIBE_MODEL", "gemini-3.6-flash")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OFFSET_FILE = os.path.join(os.path.dirname(__file__), "offset.txt")
MESSAGE_MAP_FILE = os.path.join(os.path.dirname(__file__), "message_map.json")
ALLOWED_USER_IDS = {
    int(value.strip())
    for value in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if value.strip()
}

# prefix -> tag mapping
PREFIX_TAGS = {
    "!link": "link",
    "!music": "music",
    "!idea": "idea",
    "!meeting": "meeting",
    "!podcast": "podcast",
    "!todo": "todo",
    "!github": "github",
    "!twitterx": "twitterX",
    "!task": "task",
}

# Host patterns for URL auto-tags (only when no !prefix matched).
URL_AUTO_TAGS = (
    (re.compile(r"https?://(?:www\.)?(?:gist\.)?github\.com/\S+", re.I), "github"),
    (re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/\S+", re.I), "twitterX"),
)


def build_memo_content(text: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix, tag in PREFIX_TAGS.items():
        if lowered.startswith(prefix.lower()):
            rest = stripped[len(prefix):].strip()
            if prefix == "!task":
                # Generate a Markdown task list; Memos renders "- [ ]" as
                # interactive checkboxes that can be ticked off in the WebUI.
                # Two input styles are supported:
                #   1. Bracket groups:   !task [a] [b] [c]
                #   2. One per line:     !task a\nb\nc
                bracket_items = re.findall(r"\[([^\[\]]+)\]", rest)
                if bracket_items:
                    items = [item.strip() for item in bracket_items if item.strip()]
                else:
                    items = [line.strip() for line in rest.splitlines() if line.strip()]
                if not items:
                    return "#task"
                tasks = "\n".join(f"- [ ] {item}" for item in items)
                return f"#task\n{tasks}"
            return f"#{tag} {rest}".strip()
    for pattern, tag in URL_AUTO_TAGS:
        if pattern.search(stripped):
            return f"#{tag} {stripped}".strip()
    return f"#inbox {stripped}".strip()


def load_offset() -> int:
    if os.path.exists(OFFSET_FILE):
        with open(OFFSET_FILE) as f:
            return int(f.read().strip() or 0)
    return 0


def save_offset(offset: int) -> None:
    with open(OFFSET_FILE, "w") as f:
        f.write(str(offset))


def load_message_map() -> dict:
    """Maps a Telegram message_id (str) -> Memos memo name, e.g. 'memos/abc123'."""
    if os.path.exists(MESSAGE_MAP_FILE):
        with open(MESSAGE_MAP_FILE) as f:
            return json.load(f)
    return {}


def save_message_map(message_map: dict) -> None:
    with open(MESSAGE_MAP_FILE, "w") as f:
        json.dump(message_map, f)


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


GITHUB_REPO_URL_RE = re.compile(
    r"https?://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git|/)?(?:\s|$)"
)


def get_github_repo_info(owner: str, repo: str) -> dict | None:
    """Fetch basic repo metadata from the public GitHub API (unauthenticated)."""
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


def enrich_with_github_metadata(content: str) -> str:
    match = GITHUB_REPO_URL_RE.search(content)
    if not match:
        return content
    owner, repo = match.group(1), match.group(2)
    info = get_github_repo_info(owner, repo)
    if not info:
        return content
    description = info.get("description") or ""
    stars = info.get("stargazers_count", 0)
    language = info.get("language") or ""
    full_name = info.get("full_name", f"{owner}/{repo}")
    details = " · ".join(filter(None, [language, f"⭐ {stars}"]))
    header = f"🐙 {full_name}"
    if description:
        header += f" — {description}"
    if details:
        header += f" ({details})"
    return f"{header}\n{content}"


TWITTER_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([\w]+)/status/(\d+)",
    re.IGNORECASE
)


def get_twitter_status_info(username: str, status_id: str) -> dict | None:
    """Fetch tweet metadata from the public fxtwitter API (no auth required)."""
    try:
        resp = requests.get(
            f"https://api.fxtwitter.com/{username}/status/{status_id}",
            headers={"User-Agent": "Memos-Telegram-Bot/1.0"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("tweet")
    except requests.RequestException:
        return None


def enrich_with_twitter_metadata(content: str) -> str:
    match = TWITTER_STATUS_URL_RE.search(content)
    if not match:
        return content
    username, status_id = match.group(1), match.group(2)
    info = get_twitter_status_info(username, status_id)
    if not info:
        return content
    author_name = info.get("author", {}).get("screen_name", username)
    text = info.get("text", "")
    if not text:
        return content
    truncated_text = text[:200].strip()
    if len(text) > 200:
        truncated_text += "…"
    likes = info.get("likes", 0)
    views = info.get("views", 0)
    details_parts = []
    if likes > 0:
        details_parts.append(f"❤️ {likes}")
    if views > 0:
        details_parts.append(f"👁️ {views}")
    details = " · ".join(details_parts)
    header = f"🐦 @{author_name}: {truncated_text}"
    if details:
        header += f" ({details})"
    return f"{header}\n{content}"


# A caption/text starting with this prefix (on any message) requests that
# any attached audio be transcribed via Gemini. The prefix itself is
# stripped from the caption before it's parsed as a normal !prefix tag.
TRANSCRIBE_PREFIX = "!txt"

# MIME types Gemini's generateContent audio input accepts.
TRANSCRIBABLE_MIME_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mp3", "audio/mpeg", "audio/aiff",
    "audio/aac", "audio/ogg", "audio/flac", "audio/x-flac", "audio/x-m4a",
    "audio/mp4",
}


def strip_transcribe_prefix(text: str) -> tuple[bool, str]:
    """Detects a leading !txt and returns (should_transcribe, remaining_text)."""
    stripped = text.strip()
    if stripped.lower().startswith(TRANSCRIBE_PREFIX):
        return True, stripped[len(TRANSCRIBE_PREFIX):].strip()
    return False, text


def transcribe_with_gemini(data: bytes, mime_type: str) -> str | None:
    """Transcribes audio bytes via the Gemini generateContent API. Returns the
    transcript text, or None if transcription is unavailable/failed."""
    if not GEMINI_API_KEY:
        print("!txt requested but GEMINI_API_KEY is not configured; skipping transcription.")
        return None
    if mime_type not in TRANSCRIBABLE_MIME_TYPES:
        print(f"!txt requested but mime type {mime_type!r} is not transcribable; skipping.")
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TRANSCRIBE_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{
                    "parts": [
                        {
                            "text": (
                                "Transcribe the audio accurately. Return only the "
                                "transcript text, in the original spoken language. "
                                "Do not summarize, translate, or add commentary."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(data).decode("ascii"),
                            }
                        },
                    ]
                }]
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        candidates = result.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts).strip()
        return text or None
    except requests.RequestException as exc:
        print(f"Gemini transcription failed: {exc}")
        return None


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


def create_comment(memo_name: str, content: str) -> str:
    """Creates a comment on an existing memo. memo_name is e.g. 'memos/abc123'."""
    resp = requests.post(
        f"{MEMOS_URL}/api/v1/{memo_name}/comments",
        headers={
            "Authorization": f"Bearer {MEMOS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"content": content, "visibility": "PRIVATE"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["name"]


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


# Message field -> automatic tag, applied regardless of any !prefix, so
# e.g. every voice message you send yourself gets #voice.
AUTO_TAGS = {
    "photo": "photo",
    "voice": "voice",
    "video_note": "video",
    "video": "video",
    "audio": "audio",
    "document": "file",
}


def get_auto_tag(message: dict) -> str | None:
    if "photo" in message:
        return AUTO_TAGS["photo"]
    for field in FILE_FIELDS:
        if field in message:
            return AUTO_TAGS[field]
    return None


def add_auto_tag(content: str, tag: str | None) -> str:
    if not tag:
        return content
    hashtag = f"#{tag}"
    if hashtag in content.split():
        return content
    # Insert right after the first existing tag/word so #inbox #voice ...
    # reads naturally, e.g. "#inbox #voice message text".
    parts = content.split(" ", 1)
    if parts[0].startswith("#"):
        rest = parts[1] if len(parts) > 1 else ""
        return f"{parts[0]} {hashtag} {rest}".strip()
    return f"{hashtag} {content}".strip()


def handle_update(update: dict, message_map: dict) -> None:
    message = update.get("message")
    if not message:
        return

    user_id = message.get("from", {}).get("id")
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        print(f"Ignored message from unauthorized Telegram user {user_id!r}")
        return

    text = message.get("text") or message.get("caption") or ""
    reply_to = message.get("reply_to_message")
    parent_memo_name = None
    if reply_to:
        parent_memo_name = message_map.get(str(reply_to["message_id"]))

    # Telegram voice messages (the round mic-button recordings) can't carry a
    # caption at all, so "!txt" can't be attached directly to them. Instead,
    # replying "!txt" to an already-bridged voice/audio message transcribes
    # *that* message's audio and posts the transcript as a comment.
    if parent_memo_name and text.strip().lower() == TRANSCRIBE_PREFIX and reply_to:
        reply_file_info = extract_file(reply_to)
        if reply_file_info:
            reply_file_id, _, reply_mime_type = reply_file_info
            reply_data, _ = download_telegram_file(reply_file_id)
            transcript = transcribe_with_gemini(reply_data, reply_mime_type)
            comment_content = f"📝 {transcript}" if transcript else "⚠️ !txt: transcription failed or unavailable"
            comment_name = create_comment(parent_memo_name, comment_content)
            message_map[str(message["message_id"])] = comment_name
            save_message_map(message_map)
            print(f"Transcribed reply-audio -> comment on {parent_memo_name}: {comment_content!r}")
            return
        # No audio found on the replied-to message -> fall through to the
        # normal reply-as-comment handling below (treats "!txt" as plain text).

    should_transcribe, text = strip_transcribe_prefix(text)

    auto_tag = get_auto_tag(message)

    # Download the attached file (if any) up front so a requested
    # transcription can be folded into the memo/comment content below.
    file_info = extract_file(message)
    file_data = None
    if file_info:
        file_id, filename, mime_type = file_info
        file_data, _ = download_telegram_file(file_id)

    transcript = None
    if should_transcribe and file_data is not None:
        transcript = transcribe_with_gemini(file_data, mime_type)
        if transcript:
            print(f"Transcribed audio ({len(file_data)} bytes) -> {transcript!r}")

    if parent_memo_name:
        # This message is a reply to a message we've already turned into a
        # memo -> file it as a comment on that memo instead of a new memo.
        comment_content = add_auto_tag(text or "(file)", auto_tag)
        if transcript:
            comment_content = f"{comment_content}\n\n📝 {transcript}"
        comment_name = create_comment(parent_memo_name, comment_content)
        print(f"Saved comment on {parent_memo_name}: {comment_content!r}")
        memo_name = comment_name  # attachments on a reply go on the comment
    else:
        content = build_memo_content(text) if text else "#inbox (file)"
        content = add_auto_tag(content, auto_tag)
        content = enrich_with_youtube_metadata(content)
        content = enrich_with_github_metadata(content)
        content = enrich_with_twitter_metadata(content)
        if transcript:
            content = f"{content}\n\n📝 {transcript}"
        memo_name = create_memo(content)
        print(f"Saved memo: {content!r}")

    message_map[str(message["message_id"])] = memo_name
    save_message_map(message_map)

    if file_info and file_data is not None:
        _, filename, mime_type = file_info
        try:
            attach_file_to_memo(memo_name, filename, mime_type, file_data)
            print(f"Attached file {filename!r} ({len(file_data)} bytes) to {memo_name}")
        except requests.RequestException as exc:
            print(f"Failed to attach file {filename!r} to {memo_name}: {exc}")


def main() -> None:
    offset = load_offset()
    message_map = load_message_map()
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
                update_id = update["update_id"]
                try:
                    handle_update(update, message_map)
                except Exception as exc:  # noqa: BLE001 - keep the bridge alive even on transient API errors.
                    print(f"Error handling Telegram update {update_id}: {exc}")
                finally:
                    offset = update_id + 1
                    save_offset(offset)
        except requests.RequestException as exc:
            print(f"Error polling Telegram: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
