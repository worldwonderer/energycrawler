# Energy Browser Client

A Python client library for the Energy Browser Service.

## Installation

```bash
pip install grpcio grpcio-tools
```

## Usage

### Basic Usage

```python
from energy_client import BrowserClient, Cookie

# Create client
client = BrowserClient(host='localhost', port=50051)
client.connect()

# Create browser
client.create_browser('my-browser', headless=True)

# Navigate
status = client.navigate('my-browser', 'https://example.com')
print(f"Status: {status}")

# Get cookies
cookies = client.get_cookies('my-browser', 'https://example.com')
for cookie in cookies:
    print(f"Cookie: {cookie.name}={cookie.value}")

# Close browser
client.close_browser('my-browser')
client.disconnect()
```

### Context Manager

```python
from energy_client import BrowserClient

with BrowserClient() as client:
    client.create_browser('my-browser')
    client.navigate('my-browser', 'https://example.com')
    # Browser automatically closed on exit
```

### Using the Interface

```python
from energy_client import create_browser_backend, Cookie

# Create backend
backend = create_browser_backend('energy', host='localhost', port=50051)

with backend:
    backend.create_browser('my-browser')
    backend.navigate('my-browser', 'https://example.com')

    # Set cookies
    cookies = [
        Cookie(name='session', value='abc123', domain='example.com')
    ]
    backend.set_cookies('my-browser', cookies)
```

### Platform Signatures

```python
from energy_client import BrowserClient

with BrowserClient() as client:
    client.create_browser('xhs-browser')
    client.navigate('xhs-browser', 'https://www.xiaohongshu.com')

    # Execute signature generation for XHS
    signatures = client.execute_signature('xhs-browser', 'xhs',
                                          'https://www.xiaohongshu.com/api/...')
    print(f"Signatures: {signatures}")
```

## API Reference

### BrowserClient

Main client class for communicating with the Energy service.

#### Methods

- `connect()` - Establish connection to service
- `disconnect()` - Close connection
- `create_browser(browser_id, headless=True)` - Create browser instance
- `close_browser(browser_id)` - Close browser instance
- `navigate(browser_id, url, timeout_ms=30000)` - Navigate to URL
- `get_cookies(browser_id, url)` - Get cookies for URL
- `set_cookies(browser_id, cookies)` - Set cookies
- `execute_js(browser_id, script)` - Execute JavaScript
- `set_proxy(browser_id, proxy_url, username='', password='')` - Set proxy
- `execute_signature(browser_id, platform, url)` - Execute signature generation

### BrowserInterface

Abstract interface for browser backends. Implementations:
- `EnergyBrowserBackend` - Energy gRPC backend

### Cookie

Dataclass representing an HTTP cookie.

```python
@dataclass
class Cookie:
    name: str
    value: str
    domain: str
    path: str
    secure: bool
    http_only: bool
```

## Development

### Generate Protobuf Files

```bash
python -m grpc_tools.protoc -I../energy-service/proto \
    --python_out=. \
    --grpc_python_out=. \
    ../energy-service/proto/browser.proto
```

## License

MIT License
