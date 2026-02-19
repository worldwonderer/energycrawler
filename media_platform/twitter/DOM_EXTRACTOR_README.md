# Twitter DOM Extractor Documentation

## Overview

The Twitter DOM Extractor is a powerful tool for extracting tweets from Twitter/X.com without requiring login credentials. It uses the Energy browser service to navigate Twitter pages and JavaScript to extract data directly from the DOM.

## Features

- **No Login Required**: Extract public tweets, user profiles, and replies without authentication
- **Timeline Extraction**: Get user timelines with automatic scrolling to load more tweets
- **Tweet Details**: Extract detailed information about specific tweets
- **User Profiles**: Get user profile information including bio, follower counts, etc.
- **Tweet Replies**: Extract replies to specific tweets
- **Media Detection**: Automatically detect and extract image and video URLs
- **Engagement Metrics**: Extract likes, retweets, replies, views, and bookmarks

## Architecture

```
TwitterDOMExtractor
    ├── Browser Client (Energy Browser Backend)
    ├── JavaScript Extraction Scripts
    │   ├── Timeline Extraction
    │   ├── Tweet Detail Extraction
    │   └── User Profile Extraction
    └── TweetData Dataclass
```

## Installation

Ensure the Energy browser service is running:

```bash
cd energy-service
python -m grpc_server
```

## Usage

### Basic Usage

```python
from media_platform.twitter.dom_extractor import TwitterDOMExtractor
from energy_client.browser_interface import EnergyBrowserBackend
import asyncio

async def main():
    # Create browser backend
    backend = EnergyBrowserBackend(host='localhost', port=50051)
    browser_id = "twitter_extractor"

    # Connect and create browser
    backend.connect()
    backend.create_browser(browser_id, headless=True)

    # Navigate to Twitter
    backend.navigate(browser_id, "https://x.com", timeout_ms=30000)
    await asyncio.sleep(3)

    # Create DOM extractor
    extractor = TwitterDOMExtractor(backend, browser_id)

    # Extract tweets
    tweets = await extractor.get_user_timeline("elonmusk", count=20)

    for tweet in tweets:
        print(f"@{tweet.user_screen_name}: {tweet.text[:50]}...")

    # Cleanup
    backend.disconnect()

asyncio.run(main())
```

### Using with TwitterCrawler

The DOM extractor is integrated into `TwitterCrawler` and can be used as a fallback when API authentication is not available:

```python
from media_platform.twitter import TwitterCrawler
import asyncio

async def main():
    crawler = TwitterCrawler()
    await crawler._init_energy_adapter()

    # Use DOM extraction (no login required)
    tweets = await crawler.get_user_timeline_dom(
        screen_name="elonmusk",
        count=20,
        scroll_times=3
    )

    for tweet in tweets:
        print(f"Tweet {tweet.id}: {tweet.text[:50]}...")

asyncio.run(main())
```

## API Reference

### TweetData

Dataclass representing extracted tweet data.

```python
@dataclass
class TweetData:
    id: str                              # Tweet ID
    user_name: str                       # Display name
    user_screen_name: str                # Username (without @)
    text: str                            # Tweet text
    created_at: Optional[str] = None     # ISO timestamp
    likes: int = 0                       # Like count
    retweets: int = 0                    # Retweet count
    replies: int = 0                     # Reply count
    views: int = 0                       # View count
    quotes: int = 0                      # Quote count
    bookmarks: int = 0                   # Bookmark count
    has_media: bool = False              # Has media attachments
    images: List[str] = field(default_factory=list)   # Image URLs
    videos: List[str] = field(default_factory=list)   # Video URLs
    url: str = ""                        # Tweet URL
    is_retweet: bool = False             # Is retweet
    is_reply: bool = False               # Is reply
    reply_to_id: Optional[str] = None    # Original tweet ID (if reply)
    reply_to_user: Optional[str] = None  # Original user (if reply)
```

### TwitterDOMExtractor

Main class for extracting data from Twitter DOM.

#### Constructor

```python
TwitterDOMExtractor(browser_client, browser_id: str)
```

**Parameters:**
- `browser_client`: Energy browser client instance
- `browser_id`: Browser instance ID

#### Methods

##### get_user_timeline()

Extract tweets from a user's timeline.

```python
async def get_user_timeline(
    self,
    screen_name: str,
    count: int = 20,
    scroll_times: int = 3
) -> List[TweetData]
```

**Parameters:**
- `screen_name`: Twitter username (without @)
- `count`: Maximum number of tweets to return (default: 20)
- `scroll_times`: Number of times to scroll to load more tweets (default: 3)

**Returns:**
- List of `TweetData` objects

**Example:**
```python
tweets = await extractor.get_user_timeline("elonmusk", count=50, scroll_times=5)
```

##### get_tweet_detail()

Extract details of a specific tweet.

```python
async def get_tweet_detail(
    self,
    screen_name: str,
    tweet_id: str
) -> Optional[TweetData]
```

**Parameters:**
- `screen_name`: Tweet author's username
- `tweet_id`: Tweet ID

**Returns:**
- `TweetData` object or `None` if not found

**Example:**
```python
tweet = await extractor.get_tweet_detail("elonmusk", "1234567890")
if tweet:
    print(f"Likes: {tweet.likes}, Views: {tweet.views}")
```

##### get_user_profile()

Extract user profile information.

```python
async def get_user_profile(
    self,
    screen_name: str
) -> Optional[Dict[str, Any]]
```

**Parameters:**
- `screen_name`: Twitter username (without @)

**Returns:**
- Dictionary with profile data or `None` if not found

**Profile Fields:**
- `screen_name`: Username
- `name`: Display name
- `bio`: Bio text
- `location`: Location
- `website`: Website URL
- `avatar_url`: Profile image URL
- `banner_url`: Banner image URL
- `following_count`: Following count
- `followers_count`: Followers count

**Example:**
```python
profile = await extractor.get_user_profile("elonmusk")
if profile:
    print(f"Followers: {profile['followers_count']}")
```

##### get_tweet_replies()

Extract replies to a tweet.

```python
async def get_tweet_replies(
    self,
    screen_name: str,
    tweet_id: str,
    count: int = 20
) -> List[TweetData]
```

**Parameters:**
- `screen_name`: Tweet author's username
- `tweet_id`: Tweet ID
- `count`: Maximum number of replies to return (default: 20)

**Returns:**
- List of `TweetData` objects (replies)

**Example:**
```python
replies = await extractor.get_tweet_replies("elonmusk", "1234567890", count=30)
for reply in replies:
    print(f"@{reply.user_screen_name}: {reply.text}")
```

##### scroll_for_more_tweets()

Scroll the page to load more tweets.

```python
async def scroll_for_more_tweets(self, times: int = 3) -> None
```

**Parameters:**
- `times`: Number of times to scroll (default: 3)

**Example:**
```python
await extractor.scroll_for_more_tweets(times=5)
```

## Integration with TwitterCrawler

The DOM extractor is fully integrated into `TwitterCrawler` and provides alternative methods that don't require authentication:

### DOM Extraction Methods in TwitterCrawler

```python
# Get user timeline via DOM
tweets = await crawler.get_user_timeline_dom(
    screen_name="elonmusk",
    count=20,
    scroll_times=3
)

# Get tweet detail via DOM
tweet = await crawler.get_tweet_detail_dom("elonmusk", "1234567890")

# Get user profile via DOM
profile = await crawler.get_user_profile_dom("elonmusk")

# Get tweet replies via DOM
replies = await crawler.get_tweet_replies_dom("elonmusk", "1234567890", count=20)
```

## Limitations

1. **Rate Limiting**: Twitter may rate-limit requests even without login
2. **Content Visibility**: Only public tweets and profiles can be extracted
3. **JavaScript Required**: Requires JavaScript-enabled browser (Energy service)
4. **Dynamic Content**: Twitter's DOM structure may change, requiring selector updates
5. **Pagination**: Limited by scrolling mechanism (can't access very old tweets easily)

## Best Practices

1. **Rate Limiting**: Add delays between requests to avoid rate limiting
   ```python
   await asyncio.sleep(2)  # Add delay between requests
   ```

2. **Error Handling**: Always wrap calls in try-except blocks
   ```python
   try:
       tweets = await extractor.get_user_timeline("elonmusk")
   except Exception as e:
       print(f"Error: {e}")
   ```

3. **Headless Mode**: Use headless mode for production
   ```python
   backend.create_browser(browser_id, headless=True)
   ```

4. **Cleanup**: Always disconnect the browser when done
   ```python
   try:
       # ... extraction code ...
   finally:
       backend.disconnect()
   ```

5. **Scroll Times**: Adjust scroll times based on how many tweets you need
   ```python
   # For more tweets, increase scroll_times
   tweets = await extractor.get_user_timeline("user", scroll_times=10)
   ```

## Troubleshooting

### No tweets extracted

**Cause:** Page didn't load completely or Twitter detected automation.

**Solution:**
- Increase wait time after navigation
- Use non-headless mode to debug
- Check if Energy service is running

### Incomplete data

**Cause:** DOM selectors are outdated.

**Solution:**
- Update JavaScript selectors in `dom_extractor.py`
- Check Twitter's current DOM structure using browser DevTools

### Connection errors

**Cause:** Energy service not running or wrong port.

**Solution:**
```bash
# Check if Energy service is running
lsof -i :50051

# Start Energy service
cd energy-service
python -m grpc_server
```

## Examples

See `media_platform/twitter/example_dom_extractor.py` for complete working examples.

## License

This code is for learning and research purposes only. See the LICENSE file for details.
