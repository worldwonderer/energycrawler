#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example: Using Twitter DOM Extractor

This example demonstrates how to use the TwitterDOMExtractor
to scrape tweets without requiring login credentials.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from media_platform.twitter.dom_extractor import TwitterDOMExtractor, TweetData
from energy_client.browser_interface import EnergyBrowserBackend


async def example_get_user_timeline():
    """Example: Get user timeline without login."""
    print("=" * 60)
    print("Example: Get User Timeline (No Login Required)")
    print("=" * 60)

    # Create Energy browser backend
    backend = EnergyBrowserBackend(host='localhost', port=50051)
    browser_id = "twitter_dom_extractor"

    try:
        # Connect and create browser
        backend.connect()
        backend.create_browser(browser_id, headless=False)

        # Navigate to Twitter
        backend.navigate(browser_id, "https://x.com", timeout_ms=30000)
        await asyncio.sleep(3)

        # Create DOM extractor
        extractor = TwitterDOMExtractor(backend, browser_id)

        # Get user timeline
        screen_name = "elonmusk"  # Example: Elon Musk's Twitter
        tweets = await extractor.get_user_timeline(
            screen_name=screen_name,
            count=10,
            scroll_times=2
        )

        # Display results
        print(f"\nExtracted {len(tweets)} tweets from @{screen_name}:\n")
        for i, tweet in enumerate(tweets, 1):
            print(f"{i}. Tweet ID: {tweet.id}")
            print(f"   Text: {tweet.text[:100]}...")
            print(f"   Likes: {tweet.likes}, Retweets: {tweet.retweets}, Replies: {tweet.replies}")
            print(f"   Has Media: {tweet.has_media}")
            print(f"   URL: {tweet.url}")
            print()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        try:
            backend.disconnect()
        except:
            pass


async def example_get_tweet_detail():
    """Example: Get tweet details without login."""
    print("=" * 60)
    print("Example: Get Tweet Detail (No Login Required)")
    print("=" * 60)

    # Create Energy browser backend
    backend = EnergyBrowserBackend(host='localhost', port=50051)
    browser_id = "twitter_dom_extractor"

    try:
        # Connect and create browser
        backend.connect()
        backend.create_browser(browser_id, headless=False)

        # Navigate to Twitter
        backend.navigate(browser_id, "https://x.com", timeout_ms=30000)
        await asyncio.sleep(3)

        # Create DOM extractor
        extractor = TwitterDOMExtractor(backend, browser_id)

        # Get tweet detail
        screen_name = "elonmusk"
        tweet_id = "1234567890"  # Replace with actual tweet ID
        tweet = await extractor.get_tweet_detail(screen_name, tweet_id)

        if tweet:
            print(f"\nTweet Details:")
            print(f"  ID: {tweet.id}")
            print(f"  User: @{tweet.user_screen_name} ({tweet.user_name})")
            print(f"  Text: {tweet.text}")
            print(f"  Likes: {tweet.likes}")
            print(f"  Retweets: {tweet.retweets}")
            print(f"  Replies: {tweet.replies}")
            print(f"  Views: {tweet.views}")
            print(f"  Bookmarks: {tweet.bookmarks}")
            print(f"  Images: {len(tweet.images)}")
            print(f"  Videos: {len(tweet.videos)}")
            print(f"  URL: {tweet.url}")
        else:
            print("Tweet not found")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        try:
            backend.disconnect()
        except:
            pass


async def example_get_user_profile():
    """Example: Get user profile without login."""
    print("=" * 60)
    print("Example: Get User Profile (No Login Required)")
    print("=" * 60)

    # Create Energy browser backend
    backend = EnergyBrowserBackend(host='localhost', port=50051)
    browser_id = "twitter_dom_extractor"

    try:
        # Connect and create browser
        backend.connect()
        backend.create_browser(browser_id, headless=False)

        # Navigate to Twitter
        backend.navigate(browser_id, "https://x.com", timeout_ms=30000)
        await asyncio.sleep(3)

        # Create DOM extractor
        extractor = TwitterDOMExtractor(backend, browser_id)

        # Get user profile
        screen_name = "elonmusk"
        profile = await extractor.get_user_profile(screen_name)

        if profile:
            print(f"\nUser Profile:")
            print(f"  Screen Name: @{profile['screen_name']}")
            print(f"  Name: {profile['name']}")
            print(f"  Bio: {profile['bio'][:100]}...")
            print(f"  Location: {profile['location']}")
            print(f"  Website: {profile['website']}")
            print(f"  Followers: {profile['followers_count']}")
            print(f"  Following: {profile['following_count']}")
            print(f"  Avatar: {profile['avatar_url'][:50]}...")
        else:
            print("Profile not found")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        try:
            backend.disconnect()
        except:
            pass


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Twitter DOM Extractor Examples")
    print("=" * 60 + "\n")

    # Example 1: Get user timeline
    await example_get_user_timeline()

    # Example 2: Get tweet detail
    # await example_get_tweet_detail()

    # Example 3: Get user profile
    # await example_get_user_profile()

    print("\nExamples completed!")


if __name__ == "__main__":
    asyncio.run(main())
