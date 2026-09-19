# Twitter/X URL Enrichment

## Overview

The Telegram bot now automatically enriches Twitter/X status URLs with contextual metadata, similar to how it handles YouTube videos and GitHub repositories. When a tweet URL is posted, the bot fetches and prepends author information, tweet text, and engagement stats.

## Implementation Details

### API Choice: fxtwitter.com

- **No API keys required**: Uses the public fxtwitter.com API
- **Endpoint**: `https://api.fxtwitter.com/{username}/status/{id}`
- **Timeout**: 8 seconds (short to avoid blocking)
- **Graceful degradation**: Falls back to original content on failure

### URL Pattern Matching

The enrichment supports various Twitter/X URL formats:
- `https://x.com/username/status/123456`
- `https://twitter.com/username/status/123456`
- `https://www.x.com/username/status/123456`
- `https://mobile.twitter.com/username/status/123456`

**Note**: Profile-only URLs (e.g., `https://x.com/username`) are not enriched.

### Enrichment Format

```
🐦 @{screen_name}: {tweet_text} (❤️ {likes} · 👁️ {views})
{original_content}
```

Example:
```
🐦 @elonmusk: Excited to announce our latest innovation! (❤️ 15420 · 👁️ 342891)
#twitterX https://x.com/elonmusk/status/1234567890
```

### Features

1. **Text Truncation**: Tweets longer than 200 characters are truncated with "…"
2. **Engagement Stats**: Displays likes and views when available
3. **Auto-tagging**: The existing `#twitterX` auto-tag continues to work
4. **Manual tags**: Both `!twitterx` and `!twitterX` prefixes are supported

## Files Modified

### `bot.py` (55 additions, 2 deletions)

1. **Updated docstring** (lines 26-29): Added Twitter enrichment documentation
2. **Added regex pattern** (lines 213-216): `TWITTER_STATUS_URL_RE`
3. **Added API function** (lines 219-232): `get_twitter_status_info()`
4. **Added enrichment** (lines 235-261): `enrich_with_twitter_metadata()`
5. **Integrated enrichment** (line 520): Called before memo creation

### `test_bot.py` (150 additions, new file)

Comprehensive test suite with 10 unit tests:
- ✅ URL regex matching (x.com, twitter.com, www, mobile)
- ✅ Enrichment with successful API response
- ✅ Long text truncation
- ✅ API failure handling
- ✅ No URL in content
- ✅ Empty tweet text handling

### `demo_twitter_enrichment.py` (117 additions, new file)

Demo script showing enrichment behavior with mock data:
- Example 1: Tweet with engagement stats
- Example 2: Long tweet (truncated)
- Example 3: Tweet with minimal stats
- Example 4: API failure (graceful fallback)
- Example 5: No Twitter URL (skip enrichment)

## Testing

### Run Unit Tests
```bash
cd integrations/telegram-bot
python3 test_bot.py -v
```

Expected output: All 10 tests pass

### Run Demo
```bash
cd integrations/telegram-bot
python3 demo_twitter_enrichment.py
```

Shows 5 example scenarios with formatted output.

## Usage

The enrichment happens automatically when:

1. **Auto-tagging**: Any message containing a Twitter/X status URL
   ```
   Input:  https://x.com/someone/status/123
   Result: #twitterX with enriched header + URL
   ```

2. **Manual prefix**: Using `!twitterx` or `!twitterX`
   ```
   Input:  !twitterX https://x.com/someone/status/123
   Result: #twitterX with enriched header + URL
   ```

3. **Combined with other tags**: Works with existing tag logic
   ```
   Input:  !link https://x.com/someone/status/123
   Result: #link with enriched header + URL
   ```

## Error Handling

The enrichment is resilient to failures:

- **API timeout**: Returns original content unchanged
- **HTTP errors**: Returns original content unchanged
- **Missing tweet text**: Returns original content unchanged
- **Profile-only URLs**: Skips enrichment (no status ID)
- **Network issues**: Returns original content unchanged

No error is fatal; the bot continues to operate normally even if enrichment fails.

## Dependencies

No new dependencies added. Uses existing `requests` library from `requirements.txt`.

## Future Enhancements (Optional)

Potential improvements not included in this PR:
- Cache tweet metadata to reduce API calls
- Add retweet/reply counts to stats
- Support quote tweets with different formatting
- Add media indicators (🎥 for videos, 📸 for images)
- Support Twitter Lists URLs

## Pull Request

- **Branch**: `cursor/twitter-enrichment-9c08`
- **Base**: `feature/telegram-inbox`
- **PR**: https://github.com/kwanka369/memos/pull/2
- **Status**: Open, ready for review
- **Commits**: 2 commits, 322 additions, 2 deletions
