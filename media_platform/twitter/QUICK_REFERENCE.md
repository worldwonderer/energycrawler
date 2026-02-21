# Twitter DOM Extractor - Quick Reference

## 🚀 Quick Start

```python
from media_platform.twitter.dom_extractor import TwitterDOMExtractor
from energy_client.browser_interface import EnergyBrowserBackend
import asyncio

async def main():
    # Setup
    backend = EnergyBrowserBackend(host='localhost', port=50051)
    backend.create_browser("twitter", headless=True)
    backend.navigate("twitter", "https://x.com", 30000)
    await asyncio.sleep(3)

    # Extract
    extractor = TwitterDOMExtractor(backend, "twitter")
    tweets = await extractor.get_user_timeline("elonmusk", count=20)

    # Process
    for tweet in tweets:
        print(f"@{tweet.user_screen_name}: {tweet.text[:50]}...")

    # Cleanup
    backend.disconnect()

asyncio.run(main())
```

## 📋 Main Methods

| Method | Purpose | Login Required |
|--------|---------|----------------|
| `get_user_timeline(screen_name, count, scroll_times)` | Get user's tweets | ❌ No |
| `get_tweet_detail(screen_name, tweet_id)` | Get tweet details | ❌ No |
| `get_user_profile(screen_name)` | Get user profile | ❌ No |
| `get_tweet_replies(screen_name, tweet_id, count)` | Get tweet replies | ❌ No |

## 📊 TweetData Fields

```python
TweetData(
    id: str,                    # Tweet ID
    user_name: str,             # Display name
    user_screen_name: str,      # Username (@handle)
    text: str,                  # Tweet text
    created_at: str,            # Timestamp
    likes: int,                 # Like count
    retweets: int,              # Retweet count
    replies: int,               # Reply count
    views: int,                 # View count
    bookmarks: int,             # Bookmark count
    has_media: bool,            # Has attachments
    images: List[str],          # Image URLs
    videos: List[str],          # Video URLs
    url: str,                   # Tweet URL
    is_retweet: bool,           # Is retweet
    is_reply: bool              # Is reply
)
```

## 🔧 Integration with TwitterCrawler

```python
from media_platform.twitter import TwitterCrawler

async def main():
    crawler = TwitterCrawler()
    await crawler._init_energy_adapter()

    # DOM extraction methods (no login)
    tweets = await crawler.get_user_timeline_dom("user", count=20)
    tweet = await crawler.get_tweet_detail_dom("user", "tweet_id")
    profile = await crawler.get_user_profile_dom("user")
    replies = await crawler.get_tweet_replies_dom("user", "tweet_id")

asyncio.run(main())
```

## ⚡ Common Patterns

### Get Latest Tweets from User
```python
tweets = await extractor.get_user_timeline("elonmusk", count=50, scroll_times=5)
```

### Get Tweet with All Details
```python
tweet = await extractor.get_tweet_detail("elonmusk", "1234567890")
if tweet:
    print(f"Likes: {tweet.likes}, Views: {tweet.views}")
    print(f"Media: {len(tweet.images)} images, {len(tweet.videos)} videos")
```

### Get User Profile
```python
profile = await extractor.get_user_profile("elonmusk")
if profile:
    print(f"Followers: {profile['followers_count']}")
    print(f"Bio: {profile['bio']}")
```

### Get Tweet Replies
```python
replies = await extractor.get_tweet_replies("elonmusk", "1234567890", count=30)
for reply in replies:
    print(f"@{reply.user_screen_name}: {reply.text}")
```

## ⚠️ Important Notes

1. **Energy Service Required**: Must run `python -m grpc_server` in energy-service directory
2. **Rate Limiting**: Add delays between requests: `await asyncio.sleep(2)`
3. **Public Data Only**: Cannot access private accounts or tweets
4. **Headless Mode**: Use `headless=True` for production
5. **Cleanup**: Always call `backend.disconnect()` when done

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| No tweets extracted | Increase wait time after navigation |
| Connection refused | Check Energy service is running on port 50051 |
| Incomplete data | Twitter DOM may have changed, update selectors |
| Rate limited | Add delays between requests |

## 📚 Files

- `dom_extractor.py` - Main implementation
- `example_dom_extractor.py` - Working examples
- `DOM_EXTRACTOR_README.md` - Full documentation

## 📖 Full Documentation

See `DOM_EXTRACTOR_README.md` for complete documentation including:
- Detailed API reference
- All available parameters
- Return types
- Error handling
- Best practices
- Advanced usage

---

**Need help?** Check the examples in `example_dom_extractor.py` or read the full documentation in `DOM_EXTRACTOR_README.md`.
