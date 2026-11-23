#!/usr/bin/env python3
"""Basic unit tests for bot.py enrichment functions."""
import re
import os
import unittest
from unittest.mock import patch, Mock

with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test", "MEMOS_TOKEN": "test"}):
    import bot


TWITTER_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([\w]+)/status/(\d+)",
    re.IGNORECASE
)


def enrich_with_twitter_metadata(content: str, get_twitter_status_info_fn) -> str:
    """Test-friendly version that accepts the API call as a parameter."""
    match = TWITTER_STATUS_URL_RE.search(content)
    if not match:
        return content
    username, status_id = match.group(1), match.group(2)
    info = get_twitter_status_info_fn(username, status_id)
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


class TestTwitterEnrichment(unittest.TestCase):
    def test_twitter_url_regex_x_com(self):
        """Test regex matches x.com status URLs."""
        match = TWITTER_STATUS_URL_RE.search("https://x.com/elonmusk/status/1234567890")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "elonmusk")
        self.assertEqual(match.group(2), "1234567890")

    def test_twitter_url_regex_twitter_com(self):
        """Test regex matches twitter.com status URLs."""
        match = TWITTER_STATUS_URL_RE.search("https://twitter.com/jack/status/20")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "jack")
        self.assertEqual(match.group(2), "20")

    def test_twitter_url_regex_www(self):
        """Test regex matches URLs with www prefix."""
        match = TWITTER_STATUS_URL_RE.search("https://www.x.com/user/status/999")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "user")
        self.assertEqual(match.group(2), "999")

    def test_twitter_url_regex_mobile(self):
        """Test regex matches mobile URLs."""
        match = TWITTER_STATUS_URL_RE.search("https://mobile.twitter.com/user/status/123")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "user")
        self.assertEqual(match.group(2), "123")

    def test_twitter_url_regex_no_match_profile(self):
        """Test regex doesn't match profile-only URLs."""
        match = TWITTER_STATUS_URL_RE.search("https://x.com/elonmusk")
        self.assertIsNone(match)

    def test_enrich_with_twitter_metadata_success(self):
        """Test enrichment with successful API response."""
        mock_info = {
            "author": {"screen_name": "testuser"},
            "text": "This is a test tweet!",
            "likes": 42,
            "views": 1337,
        }
        mock_get_info = Mock(return_value=mock_info)
        
        content = "#twitterX https://x.com/testuser/status/123"
        result = enrich_with_twitter_metadata(content, mock_get_info)
        
        self.assertIn("🐦 @testuser:", result)
        self.assertIn("This is a test tweet!", result)
        self.assertIn("❤️ 42", result)
        self.assertIn("👁️ 1337", result)
        self.assertIn(content, result)

    def test_enrich_with_twitter_metadata_long_text(self):
        """Test enrichment truncates long tweets."""
        long_text = "a" * 250
        mock_info = {
            "author": {"screen_name": "longuser"},
            "text": long_text,
            "likes": 0,
            "views": 0,
        }
        mock_get_info = Mock(return_value=mock_info)
        
        content = "https://x.com/longuser/status/456"
        result = enrich_with_twitter_metadata(content, mock_get_info)
        
        self.assertIn("🐦 @longuser:", result)
        self.assertIn("…", result)
        self.assertLess(len(result.split("\n")[0]), 300)

    def test_enrich_with_twitter_metadata_api_failure(self):
        """Test enrichment handles API failure gracefully."""
        mock_get_info = Mock(return_value=None)
        
        content = "#twitterX https://x.com/testuser/status/789"
        result = enrich_with_twitter_metadata(content, mock_get_info)
        
        self.assertEqual(result, content)

    def test_enrich_with_twitter_metadata_no_url(self):
        """Test enrichment with no Twitter URL in content."""
        mock_get_info = Mock()
        
        content = "#inbox Just a regular message"
        result = enrich_with_twitter_metadata(content, mock_get_info)
        
        self.assertEqual(result, content)
        mock_get_info.assert_not_called()

    def test_enrich_with_twitter_metadata_no_text(self):
        """Test enrichment when tweet has no text field."""
        mock_info = {
            "author": {"screen_name": "testuser"},
            "text": "",
            "likes": 10,
        }
        mock_get_info = Mock(return_value=mock_info)
        
        content = "https://x.com/testuser/status/999"
        result = enrich_with_twitter_metadata(content, mock_get_info)
        
        self.assertEqual(result, content)


class TestKarakeepRouting(unittest.TestCase):
    def setUp(self):
        classifier_patcher = patch.object(bot, "classify_with_gemini", return_value=None)
        self.classifier = classifier_patcher.start()
        self.addCleanup(classifier_patcher.stop)

    def test_extracts_urls_and_comment(self):
        text = "!github https://github.com/a/b. verta pabandyti"
        urls = bot.extract_http_urls(text)
        self.assertEqual(urls, ["https://github.com/a/b"])
        self.assertEqual(bot.bookmark_note(text, urls), "verta pabandyti")
        self.assertEqual(bot.karakeep_tags_for_url(urls[0], "github"), ["github"])

    def test_source_tags(self):
        self.assertEqual(bot.karakeep_tags_for_url("https://x.com/user/status/1", None), ["x"])
        self.assertEqual(
            bot.karakeep_tags_for_url("https://youtu.be/abc", "music"),
            ["youtube", "music"],
        )
        self.assertEqual(
            bot.karakeep_tags_for_url("https://example.com/a", "twitterX"),
            ["x"],
        )

    @patch.object(bot, "KARAKEEP_URL", "http://karakeep.local")
    @patch.object(bot, "KARAKEEP_API_KEY", "key")
    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_comment")
    @patch.object(bot, "analyze_with_gemini")
    @patch.object(bot, "create_memo", return_value="memos/123")
    @patch.object(bot, "enrich_with_github_metadata", side_effect=lambda content: "repo details\n" + content)
    @patch.object(bot, "create_karakeep_bookmark", return_value=True)
    def test_url_is_bookmarked_and_memo_stays_short(
        self, create_bookmark, enrich, create_memo, analyze, create_comment, save_map
    ):
        bot.handle_update(
            {"message": {"message_id": 9, "text": "!github https://github.com/a/b verta pabandyti"}},
            {},
        )
        create_bookmark.assert_called_once_with(
            "https://github.com/a/b", "verta pabandyti", ["github"]
        )
        content, space = create_memo.call_args.args
        self.assertEqual(content, "#github https://github.com/a/b verta pabandyti")
        self.assertEqual(space, bot.MEMOS_GITHUB_SPACE)
        enrich.assert_not_called()
        analyze.assert_not_called()
        create_comment.assert_not_called()

    @patch.object(bot, "KARAKEEP_URL", "http://karakeep.local")
    @patch.object(bot, "KARAKEEP_API_KEY", "key")
    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_memo", return_value="memos/123")
    @patch.object(bot, "create_karakeep_bookmark", return_value=True)
    def test_note_without_url_stays_in_memos(self, create_bookmark, create_memo, save_map):
        bot.handle_update({"message": {"message_id": 10, "text": "mintis be nuorodos"}}, {})
        create_bookmark.assert_not_called()
        self.assertIn("#inbox mintis be nuorodos", create_memo.call_args.args[0])

    @patch.object(bot, "KARAKEEP_URL", "http://karakeep.local")
    @patch.object(bot, "KARAKEEP_API_KEY", "key")
    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_comment", return_value="memos/123/comments/1")
    @patch.object(bot, "create_memo")
    @patch.object(bot, "create_karakeep_bookmark", return_value=True)
    def test_reply_with_url_stays_a_comment(self, create_bookmark, create_memo, create_comment, save_map):
        bot.handle_update(
            {"message": {
                "message_id": 12,
                "text": "žiūrėk https://example.com/a",
                "reply_to_message": {"message_id": 7},
            }},
            {"7": "memos/parent"},
        )
        create_bookmark.assert_called_once_with("https://example.com/a", "žiūrėk", [])
        create_comment.assert_called_once_with("memos/parent", "žiūrėk https://example.com/a")
        create_memo.assert_not_called()

    @patch.object(bot, "KARAKEEP_URL", "http://karakeep.local")
    @patch.object(bot, "KARAKEEP_API_KEY", "key")
    @patch.object(bot, "save_message_map")
    @patch.object(bot, "analyze_with_gemini", return_value=None)
    @patch.object(bot, "create_memo", return_value="memos/123")
    @patch.object(bot, "enrich_with_github_metadata", side_effect=lambda content: "repo details\n" + content)
    @patch.object(bot, "create_karakeep_bookmark", side_effect=bot.requests.RequestException("down"))
    def test_karakeep_failure_keeps_memo_enrichment(
        self, create_bookmark, enrich, create_memo, analyze, save_map
    ):
        bot.handle_update({"message": {"message_id": 11, "text": "!github https://github.com/a/b"}}, {})
        create_bookmark.assert_called_once()
        self.assertIn("repo details\n#github https://github.com/a/b", create_memo.call_args.args[0])


class TestGitHubEnrichment(unittest.TestCase):
    @patch.object(bot, "get_github_repo_info")
    def test_repository_urls_with_paths_and_git_suffix(self, get_repo_info):
        get_repo_info.return_value = {"full_name": "owner/widget", "description": "A tool"}
        urls = (
            "https://github.com/owner/widget",
            "https://github.com/owner/widget/tree/main/scripts",
            "https://github.com/owner/widget/blob/main/README.md",
            "https://github.com/owner/widget/issues/123",
            "https://github.com/owner/widget.git",
            "https://github.com/owner/widget.git/tree/main",
        )
        for url in urls:
            with self.subTest(url=url):
                get_repo_info.reset_mock()
                self.assertIn("🐙 owner/widget", bot.enrich_with_github_metadata(url))
                get_repo_info.assert_called_once_with("owner", "widget")


class TestTopicClassification(unittest.TestCase):
    @patch.object(bot, "GEMINI_API_KEY", "test")
    @patch.object(bot.requests, "post")
    def test_accepts_only_approved_topics(self, post):
        post.return_value.json.return_value = {"candidates": [{"content": {"parts": [{"text": (
            '{"topic":"ai-agentai","summary":"Naudingas agentų įrankis."}'
        )}]}}]}
        self.assertEqual(bot.classify_with_gemini("#github example"), ("ai-agentai", "Naudingas agentų įrankis."))
        post.return_value.json.return_value = {"candidates": [{"content": {"parts": [{"text": (
            '{"topic":"nepatvirtinta","summary":"Santrauka."}'
        )}]}}]}
        self.assertIsNone(bot.classify_with_gemini("example"))

    @patch.object(bot, "GEMINI_API_KEY", "test")
    @patch.object(bot.requests, "post")
    def test_uses_fallback_model_after_daily_quota(self, post):
        exhausted = Mock(status_code=429, ok=False)
        classified = Mock(status_code=200, ok=True)
        classified.json.return_value = {"candidates": [{"content": {"parts": [{"text": (
            '{"topic":"muzika","summary":"Muzikos radinys."}'
        )}]}}]}
        post.side_effect = [exhausted, classified]
        self.assertEqual(bot.classify_with_gemini("#music song"), ("muzika", "Muzikos radinys."))
        self.assertIn(bot.GEMINI_TRANSCRIBE_MODEL, post.call_args_list[0].args[0])
        self.assertIn(bot.GEMINI_CLASSIFY_FALLBACK_MODEL, post.call_args_list[1].args[0])


class TestMemoAnalysis(unittest.TestCase):
    def setUp(self):
        classifier_patcher = patch.object(bot, "classify_with_gemini", return_value=None)
        self.classifier = classifier_patcher.start()
        self.addCleanup(classifier_patcher.stop)

    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_comment")
    @patch.object(bot, "analyze_with_gemini")
    @patch.object(bot, "create_memo", return_value="memos/123")
    @patch.object(bot, "enrich_with_github_metadata", side_effect=lambda content: "repo details\n" + content)
    def test_github_analysis_comments_on_enriched_memo(self, enrich, create_memo, analyze, create_comment, save_map):
        analyze.return_value = "🔎 Santrauka\n💡 Nauda\ntool · try"
        message_map = {}
        bot.handle_update({"message": {"message_id": 1, "text": "!github https://github.com/a/b"}}, message_map)
        create_memo.assert_called_once_with("repo details\n#github https://github.com/a/b", bot.MEMOS_GITHUB_SPACE)
        analyze.assert_called_once_with("repo details\n#github https://github.com/a/b")
        create_comment.assert_called_once_with("memos/123", analyze.return_value)
        self.assertEqual(message_map, {"1": "memos/123"})

    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_comment")
    @patch.object(bot, "analyze_with_gemini")
    @patch.object(bot, "create_memo", return_value="memos/123")
    def test_twitter_and_inbox_routing(self, create_memo, analyze, create_comment, save_map):
        analyze.return_value = None
        bot.handle_update({"message": {"message_id": 2, "text": "!twitterx post"}}, {})
        analyze.assert_called_once_with("#twitterX post")
        create_comment.assert_not_called()
        analyze.reset_mock()
        bot.handle_update({"message": {"message_id": 3, "text": "ordinary note"}}, {})
        analyze.assert_not_called()

    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_memo", return_value="memos/123")
    def test_new_memo_keeps_source_and_adds_topic_and_status(self, create_memo, save_map):
        self.classifier.return_value = ("muzika", "Įdomi daina.")
        bot.handle_update({"message": {"message_id": 5, "text": "!music Originali žinutė"}}, {})
        content, space = create_memo.call_args.args
        self.assertEqual(space, None)
        self.assertIn("#tema/muzika #busena/nauja", content)
        self.assertIn("📝 Įdomi daina.", content)
        self.assertIn("#music Originali žinutė", content)

    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_memo", return_value="memos/123")
    def test_manual_topic_is_not_reclassified(self, create_memo, save_map):
        bot.handle_update({"message": {"message_id": 6, "text": "#tema/idejos Mano idėja"}}, {})
        self.classifier.assert_not_called()
        self.assertIn("#tema/idejos", create_memo.call_args.args[0])

    @patch.object(bot, "save_message_map")
    @patch.object(bot, "create_comment", side_effect=bot.requests.RequestException("API unavailable"))
    @patch.object(bot, "analyze_with_gemini", return_value="🔎 Santrauka\n💡 Nauda\nthread · read")
    @patch.object(bot, "create_memo", return_value="memos/123")
    def test_comment_failure_keeps_memo(self, create_memo, analyze, create_comment, save_map):
        message_map = {}
        bot.handle_update({"message": {"message_id": 4, "text": "!twitterx post"}}, message_map)
        self.assertEqual(message_map, {"4": "memos/123"})
        create_comment.assert_called_once_with("memos/123", analyze.return_value)

    @patch.object(bot, "GEMINI_API_KEY", "test")
    @patch.object(bot.requests, "post")
    def test_gemini_response_and_failure(self, post):
        post.return_value.json.return_value = {"candidates": [{"content": {"parts": [{"text": (
            '{"summary":"Repo santrauka","why_useful":"Naudingas darbui.","type":"tool","action":"try"}'
        )}]}}]}
        self.assertEqual(bot.analyze_with_gemini("#github repo"), "🔎 Repo santrauka\n💡 Naudingas darbui.\ntool · try")
        post.return_value.json.return_value = {"candidates": [{"content": {"parts": [{"text": "bad json"}]}}]}
        self.assertIsNone(bot.analyze_with_gemini("#github repo"))
        post.side_effect = bot.requests.RequestException("Gemini unavailable")
        self.assertIsNone(bot.analyze_with_gemini("#github repo"))


if __name__ == "__main__":
    unittest.main()
