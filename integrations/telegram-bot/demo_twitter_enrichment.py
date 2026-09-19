#!/usr/bin/env python3
"""
Demo script showing how Twitter enrichment works without requiring live API calls.
"""
import re


TWITTER_STATUS_URL_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([\w]+)/status/(\d+)",
    re.IGNORECASE
)


def enrich_with_twitter_metadata_demo(content: str, mock_api_data: dict | None = None) -> str:
    """Demo version with mock API data."""
    match = TWITTER_STATUS_URL_RE.search(content)
    if not match:
        return content
    
    username, status_id = match.group(1), match.group(2)
    
    if mock_api_data is None:
        return content
    
    author_name = mock_api_data.get("author", {}).get("screen_name", username)
    text = mock_api_data.get("text", "")
    if not text:
        return content
    
    truncated_text = text[:200].strip()
    if len(text) > 200:
        truncated_text += "…"
    
    likes = mock_api_data.get("likes", 0)
    views = mock_api_data.get("views", 0)
    
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


def main():
    print("=" * 80)
    print("Twitter/X Enrichment Demo")
    print("=" * 80)
    
    # Example 1: Standard tweet with stats
    print("\n📝 Example 1: Tweet with engagement stats")
    print("-" * 80)
    content1 = "#twitterX https://x.com/elonmusk/status/1234567890"
    mock_data1 = {
        "author": {"screen_name": "elonmusk"},
        "text": "Excited to announce our latest innovation in sustainable energy!",
        "likes": 15420,
        "views": 342891,
    }
    print(f"Input:  {content1}")
    print(f"Output:\n{enrich_with_twitter_metadata_demo(content1, mock_data1)}")
    
    # Example 2: Long tweet (truncation)
    print("\n📝 Example 2: Long tweet (truncated)")
    print("-" * 80)
    content2 = "https://twitter.com/threadreader/status/9876543210"
    mock_data2 = {
        "author": {"screen_name": "threadreader"},
        "text": ("This is a really long tweet that will be truncated after 200 characters. " * 5),
        "likes": 856,
        "views": 12453,
    }
    print(f"Input:  {content2}")
    print(f"Output:\n{enrich_with_twitter_metadata_demo(content2, mock_data2)}")
    
    # Example 3: Tweet with minimal stats
    print("\n📝 Example 3: Tweet with only likes")
    print("-" * 80)
    content3 = "!twitterx https://x.com/developer/status/1111111111"
    mock_data3 = {
        "author": {"screen_name": "developer"},
        "text": "Just shipped a new feature! 🚀",
        "likes": 42,
        "views": 0,
    }
    print(f"Input:  {content3}")
    print(f"Output:\n{enrich_with_twitter_metadata_demo(content3, mock_data3)}")
    
    # Example 4: API failure (graceful fallback)
    print("\n📝 Example 4: API failure (content unchanged)")
    print("-" * 80)
    content4 = "#inbox Check out https://x.com/someone/status/9999999999"
    mock_data4 = None  # API failure
    print(f"Input:  {content4}")
    print(f"Output:\n{enrich_with_twitter_metadata_demo(content4, mock_data4)}")
    
    # Example 5: No Twitter URL (skip enrichment)
    print("\n📝 Example 5: No Twitter URL (skip enrichment)")
    print("-" * 80)
    content5 = "#inbox Just a regular message about something"
    mock_data5 = None
    print(f"Input:  {content5}")
    print(f"Output:\n{enrich_with_twitter_metadata_demo(content5, mock_data5)}")
    
    print("\n" + "=" * 80)
    print("✅ All examples completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
