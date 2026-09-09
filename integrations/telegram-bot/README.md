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

| Prefix      | Tag         | Extra behavior |
|-------------|-------------|----------------|
| `!link`     | `#link`     | |
| `!music`    | `#music`    | |
| `!idea`     | `#idea`     | |
| `!meeting`  | `#meeting`  | |
| `!podcast`  | `#podcast`  | |
| `!todo`     | `#todo`     | |
| `!github`   | `#github`   | |
| `!task`     | `#task`     | Each following line becomes a Markdown task list item (`- [ ]`), rendered as interactive checkboxes in Memos |
| *(none)*    | `#inbox`    | |

Example: sending `!link https://example.com cool article` creates a memo
with content `#link https://example.com cool article`.

Example: sending
```
!task Paskambinti daktarui
Nusipirkti pieno
```
creates a memo:
```
#task
- [ ] Paskambinti daktarui
- [ ] Nusipirkti pieno
```
which renders as clickable checkboxes in Memos.

## Rich link enrichment

- **YouTube** links (`youtube.com/watch`, `youtu.be`, `.../shorts/...`) are
  enriched with the video title and channel name, fetched from YouTube's
  public oEmbed endpoint (no API key needed). Prepended as
  `🎵 <title> — <channel>`.
- **GitHub repo** links (`github.com/<owner>/<repo>`) are enriched with the
  repo description, primary language, and star count, fetched from the
  public GitHub API (no token needed, subject to GitHub's unauthenticated
  rate limits). Prepended as `🐙 <owner>/<repo> — <description> (<lang> · ⭐ N)`.

## Files, photos, voice notes

Any attached file (photo, document, voice message, audio, video note) is
downloaded from Telegram and uploaded to Memos via
`POST /api/v1/attachments`, linked to the memo created for that message.
If the message has no text/caption, the memo content defaults to
`#inbox (file)`.

## Voice transcription (`!txt`)

Telegram voice messages (the round mic-button recordings) **cannot carry a
caption at all** — that's a Telegram client limitation, not a bug here. So
there are two ways to trigger transcription, depending on what you're
sending:

**1. Reply `!txt` to a voice message you already sent** (the recommended way
for actual voice notes):

```
🎤 (send a voice message, gets tagged #voice as usual)
↳ reply to it with the text: !txt
```

The bot fetches the *original* voice message's audio, transcribes it via
Gemini, and posts the transcript as a **comment** on that memo:

```
📝 <transcribed text>
```

**2. Caption it directly with `!txt`** — this only works for file types
Telegram *does* allow captions on (uploaded audio files, videos, documents),
not native voice messages:

```
🎵 (send an audio file with caption) !txt
```

results in:

```
#inbox #audio (file)

📝 <transcribed text>
```

Requires `GEMINI_API_KEY` to be set in the bot's environment (see
`.env.example`). If the key is missing, or transcription fails for any
reason (rate limit, unsupported format, network error), the memo/comment
and audio attachment are still created as usual — just without the
transcript (or with a `⚠️` note, for the reply-based flow). The model used
is `gemini-3.6-flash` by default; override with `GEMINI_TRANSCRIBE_MODEL`.

## Replies -> Memos comments

If you reply (in Telegram) to a message that the bridge already turned
into a memo, the reply is posted as a **comment** on that memo
(`POST /api/v1/{memo}/comments`) instead of creating a new top-level memo.
This mirrors Memos' own comment feature (visible when you open a memo's
detail view and use "Write a comment").

The mapping of Telegram `message_id` -> Memos memo/comment name is kept in
`message_map.json` so replies keep working across restarts.

## Setup

1. Copy `.env.example` to `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `MEMOS_URL` — your Memos instance URL (default `http://localhost:5230`)
   - `MEMOS_TOKEN` — a Personal Access Token from Memos
     (Settings → My Account → Access Tokens)
   - `GEMINI_API_KEY` — optional, only needed for `!txt` voice transcription
     (get one at [aistudio.google.com](https://aistudio.google.com/apikey))

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run:
   ```bash
   python3 bot.py
   ```

The script keeps track of the last processed Telegram update in
`offset.txt`, and the message->memo mapping in `message_map.json`, so
neither reprocessing nor reply-tracking breaks across restarts.

## Limitations / next steps

- No retry/backoff beyond a simple 5s sleep on network errors.
- Intended to run as a single long-lived process (e.g. via `systemd`,
  `docker`, or a simple `nohup`/`screen` session), not as a one-shot script.
