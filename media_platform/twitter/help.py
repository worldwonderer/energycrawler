# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# This file is part of EnergyCrawler project.
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# Declaration: This code is for learning and research purposes only. Users should follow these principles:
# 1. Not for any commercial use.
# 2. Comply with the terms of service and robots.txt rules of the target platform.
# 3. No large-scale crawling or operational disruption to the platform.
# 4. Reasonably control request frequency to avoid unnecessary burden on the target platform.
# 5. Not for any illegal or improper purposes.
#
# For detailed license terms, please refer to the LICENSE file in the project root directory.
# Using this code means you agree to abide by the above principles and all terms in the LICENSE.

"""
Twitter/X.com Helper Functions

Utility functions for URL parsing, data extraction, and text processing
for Twitter/X.com platform.
"""

import re
from typing import Optional, List, Tuple
from urllib.parse import urlparse, parse_qs


def parse_tweet_id_from_url(url: str) -> Optional[str]:
    """
    Parse tweet ID from Twitter URL.

    Supports:
    - https://x.com/username/status/1234567890
    - https://twitter.com/username/status/1234567890
    - https://x.com/username/status/1234567890?s=20
    - Direct ID: "1234567890" (numeric string)

    Args:
        url: Tweet URL or tweet ID

    Returns:
        Tweet ID string or None if not found
    """
    # If it's a pure numeric string, return as-is
    if url.isdigit():
        return url

    # Pattern to match tweet URLs
    # Matches: x.com/username/status/1234567890 or twitter.com/username/status/1234567890
    pattern = r'(?:x\.com|twitter\.com)/\w+/status/(\d+)'

    match = re.search(pattern, url)
    if match:
        return match.group(1)

    return None


def parse_username_from_url(url: str) -> Optional[str]:
    """
    Parse username from Twitter URL.

    Supports:
    - https://x.com/username
    - https://twitter.com/username
    - https://x.com/username/status/1234567890
    - https://x.com/username/with_replies
    - Direct username: "@username" or "username"

    Args:
        url: User profile URL or username

    Returns:
        Username string (without @) or None if not found
    """
    # Remove leading @ if present
    if url.startswith('@'):
        return url[1:]

    # If it's just a username (no slashes, no http)
    if '/' not in url and not url.startswith('http'):
        return url

    # Pattern to match user URLs
    # Matches: x.com/username or twitter.com/username
    # Excludes: x.com/username/status/..., x.com/home, etc.
    pattern = r'(?:x\.com|twitter\.com)/(\w+)(?:/|$|\?)'

    match = re.search(pattern, url)
    if match:
        username = match.group(1)
        # Filter out known non-username paths
        if username not in ['home', 'explore', 'notifications', 'messages', 'bookmarks', 'settings']:
            return username

    return None


def parse_user_id_from_url(url: str) -> Optional[str]:
    """
    Parse user ID from Twitter URL (for profile URLs with user ID).

    Note: Most Twitter URLs use usernames, not user IDs. User IDs are
    typically only available in API responses.

    Args:
        url: User profile URL

    Returns:
        User ID string or None if not found
    """
    # Twitter URLs typically don't contain user IDs directly
    # This is a placeholder for future use or API response parsing
    # Pattern would be something like: x.com/user?id=123456789

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    if 'id' in params:
        return params['id'][0]

    return None


def build_tweet_url(username: str, tweet_id: str) -> str:
    """
    Build full tweet URL.

    Args:
        username: Twitter username (with or without @)
        tweet_id: Tweet ID

    Returns:
        Full tweet URL
    """
    # Remove @ from username if present
    username = username.lstrip('@')
    return f"https://x.com/{username}/status/{tweet_id}"


def build_user_url(username: str) -> str:
    """
    Build user profile URL.

    Args:
        username: Twitter username (with or without @)

    Returns:
        Full user profile URL
    """
    # Remove @ from username if present
    username = username.lstrip('@')
    return f"https://x.com/{username}"


def extract_hashtags(text: str) -> List[str]:
    """
    Extract hashtags from tweet text.

    Args:
        text: Tweet text

    Returns:
        List of hashtags (with # prefix removed, lowercase)
    """
    # Pattern: # followed by letters, numbers, underscores
    # Unicode letters are also supported
    pattern = r'#(\w+)'

    matches = re.findall(pattern, text)
    return [tag.lower() for tag in matches]


def extract_mentions(text: str) -> List[str]:
    """
    Extract @mentions from tweet text.

    Args:
        text: Tweet text

    Returns:
        List of usernames (without @ prefix, lowercase)
    """
    # Pattern: @ followed by letters, numbers, underscores
    pattern = r'@(\w+)'

    matches = re.findall(pattern, text)
    return [mention.lower() for mention in matches]


def extract_urls(text: str) -> List[str]:
    """
    Extract URLs from tweet text.

    Supports:
    - Full URLs: https://example.com/path
    - Short URLs: https://t.co/abc123

    Args:
        text: Tweet text

    Returns:
        List of URLs
    """
    # Pattern for URLs
    # Matches http:// or https:// followed by non-whitespace characters
    pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'

    matches = re.findall(pattern, text)
    return matches


def is_valid_tweet_id(tweet_id: str) -> bool:
    """
    Check if string is a valid tweet ID.

    Tweet IDs are numeric strings (Snowflake IDs).

    Args:
        tweet_id: String to check

    Returns:
        True if valid tweet ID format
    """
    if not tweet_id:
        return False

    # Tweet IDs are numeric
    if not tweet_id.isdigit():
        return False

    # Tweet IDs are typically 10+ digits (Snowflake IDs)
    # Minimum reasonable length check
    if len(tweet_id) < 10:
        return False

    return True


def is_valid_username(username: str) -> bool:
    """
    Check if string is a valid Twitter username.

    Twitter username rules:
    - 1-15 characters
    - Only letters, numbers, underscores

    Args:
        username: String to check (with or without @)

    Returns:
        True if valid username format
    """
    if not username:
        return False

    # Remove @ prefix if present
    if username.startswith('@'):
        username = username[1:]

    # Check length (1-15 characters)
    if len(username) < 1 or len(username) > 15:
        return False

    # Check characters (only letters, numbers, underscores)
    pattern = r'^\w+$'
    if not re.match(pattern, username):
        return False

    return True


def parse_tweet_url_components(url: str) -> Optional[Tuple[str, str]]:
    """
    Parse both username and tweet ID from tweet URL.

    Args:
        url: Tweet URL

    Returns:
        Tuple of (username, tweet_id) or None if parsing fails
    """
    # Pattern to match tweet URLs
    pattern = r'(?:x\.com|twitter\.com)/(\w+)/status/(\d+)'

    match = re.search(pattern, url)
    if match:
        username = match.group(1)
        tweet_id = match.group(2)
        return (username, tweet_id)

    return None


def clean_tweet_text(text: str) -> str:
    """
    Clean tweet text by removing extra whitespace and normalizing.

    Args:
        text: Raw tweet text

    Returns:
        Cleaned tweet text
    """
    if not text:
        return ""

    # Remove extra whitespace
    text = ' '.join(text.split())

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def calculate_tweet_character_count(text: str) -> int:
    """
    Calculate character count for tweet (Twitter's counting method).

    Twitter counts:
    - URLs as 23 characters (regardless of actual length)
    - Some Unicode characters as 2 characters

    This is a simplified implementation.

    Args:
        text: Tweet text

    Returns:
        Character count
    """
    if not text:
        return 0

    # Replace URLs with placeholder (23 chars)
    urls = extract_urls(text)
    temp_text = text

    for url in urls:
        # Replace each URL with 23-character placeholder
        temp_text = temp_text.replace(url, 'x' * 23, 1)

    # Count characters (simplified - doesn't handle all Unicode edge cases)
    return len(temp_text)


def is_retweet(text: str) -> bool:
    """
    Check if tweet is a retweet.

    Args:
        text: Tweet text

    Returns:
        True if tweet starts with "RT @"
    """
    if not text:
        return False

    return text.strip().startswith('RT @')


def is_reply(text: str) -> bool:
    """
    Check if tweet is a reply.

    Args:
        text: Tweet text

    Returns:
        True if tweet starts with "@"
    """
    if not text:
        return False

    return text.strip().startswith('@')


def extract_reply_to_username(text: str) -> Optional[str]:
    """
    Extract the username being replied to.

    Args:
        text: Tweet text

    Returns:
        Username being replied to (without @) or None
    """
    if not is_reply(text):
        return None

    # Extract first mention
    mentions = extract_mentions(text)
    return mentions[0] if mentions else None


if __name__ == '__main__':
    # Test URL parsing
    print("=== Tweet URL Parsing ===")
    test_urls = [
        "https://x.com/elonmusk/status/1234567890",
        "https://twitter.com/Nasa/status/9876543210?s=20",
        "1234567890",
    ]
    for url in test_urls:
        tweet_id = parse_tweet_id_from_url(url)
        print(f"URL: {url}")
        print(f"  Tweet ID: {tweet_id}\n")

    print("=== Username Parsing ===")
    test_user_urls = [
        "https://x.com/elonmusk",
        "https://twitter.com/Nasa",
        "@elonmusk",
        "elonmusk",
        "https://x.com/elonmusk/status/1234567890",
    ]
    for url in test_user_urls:
        username = parse_username_from_url(url)
        print(f"URL: {url}")
        print(f"  Username: {username}\n")

    print("=== Hashtag/Mention/URL Extraction ===")
    test_text = "Hello @elonmusk! Check out https://t.co/abc123 #SpaceX #Tesla"
    print(f"Text: {test_text}")
    print(f"  Mentions: {extract_mentions(test_text)}")
    print(f"  Hashtags: {extract_hashtags(test_text)}")
    print(f"  URLs: {extract_urls(test_text)}\n")

    print("=== Validation ===")
    print(f"is_valid_tweet_id('1234567890'): {is_valid_tweet_id('1234567890')}")
    print(f"is_valid_tweet_id('abc'): {is_valid_tweet_id('abc')}")
    print(f"is_valid_username('elonmusk'): {is_valid_username('elonmusk')}")
    print(f"is_valid_username('@elonmusk'): {is_valid_username('@elonmusk')}")
    print(f"is_valid_username('a' * 16): {is_valid_username('a' * 16)}\n")

    print("=== URL Building ===")
    print(f"build_tweet_url('elonmusk', '1234567890'): {build_tweet_url('elonmusk', '1234567890')}")
    print(f"build_user_url('@elonmusk'): {build_user_url('@elonmusk')}")
