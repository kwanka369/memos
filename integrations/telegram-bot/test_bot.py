#!/usr/bin/env python3
"""Basic unit tests for bot.py enrichment functions."""
import re
import unittest
from unittest.mock import patch, Mock


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


if __name__ == "__main__":
    unittest.main()
