"""Tests for resumable topic backfill classification."""

import os
import unittest
from unittest.mock import Mock, patch

with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test", "MEMOS_TOKEN": "test"}):
    import backfill_topics


class BackfillTopicsTest(unittest.TestCase):
    @patch.object(backfill_topics, "GEMINI_API_KEY", "test")
    @patch.object(backfill_topics.requests, "post")
    def test_batch_accepts_string_ids_and_ignores_invalid_items(self, post):
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": (
                '{"items":[{"id":"0","topic":"ai-agentai","summary":"DI įrankis."},'
                '{"id":"1","topic":"unknown","summary":"Bloga tema."}]}'
            )}]}}]
        }
        result = backfill_topics.classify_batch([{"content": "agent"}, {"content": "other"}])
        self.assertEqual(result, {0: ("ai-agentai", "DI įrankis.")})
        self.assertNotIn("key", post.call_args.kwargs.get("params", {}))

    @patch.object(backfill_topics, "GEMINI_API_KEY", "test")
    @patch.object(backfill_topics.requests, "post")
    def test_daily_quota_does_not_trigger_retries(self, post):
        response = Mock(status_code=429)
        response.raise_for_status.side_effect = backfill_topics.requests.HTTPError("quota", response=response)
        post.return_value = response
        self.assertEqual(backfill_topics.classify_batch([{"content": "item"}]), {})
        post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
