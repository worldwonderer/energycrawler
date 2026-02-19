# Energy Browser Service

A gRPC-based browser automation service built with the [Energy](https://github.com/energye/energy) framework (CEF-based) for the EnergyCrawler project.

## Overview

This service provides a high-performance, Energy-based browser automation layer that replaces the Python + DrissionPage approach with a Go + CEF (Chromium Embedded Framework) solution.

### Key Benefits

- **Performance**: Native Go performance with CEF rendering
- **Stability**: Isolated browser instances with proper lifecycle management
- **Cookie Management**: Persistent cookies with platform-specific handling
- **Anti-Detection**: Signature execution for supported platforms
- **gRPC Interface**: Language-agnostic API for Python integration

## Architecture

```
energy-service/
├── proto/          # Protocol Buffers definitions
├── server/         # gRPC server implementation
├── browser/        # Browser management logic
│   ├── manager.go      # Instance lifecycle
│   ├── cookies.go      # Cookie handling
│   ├── proxy.go        # Proxy configuration
│   ├── javascript.go   # JS execution
│   └── signature.go    # Platform signatures
└── main.go         # Service entry point
```

## Quick Start

### Prerequisites

- Go 1.21+
- Energy framework dependencies (CEF libraries)

### Build

```bash
cd energy-service
go mod tidy
go build -o energy-service
```

### Run

```bash
# Default port 50051
./energy-service

# Custom port
GRPC_PORT=:50052 ./energy-service
```

## API

### Browser Lifecycle

```protobuf
// Create a browser instance
rpc CreateBrowser(CreateBrowserRequest) returns (CreateBrowserResponse);

// Close a browser instance
rpc CloseBrowser(CloseBrowserRequest) returns (CloseBrowserResponse);
```

### Navigation

```protobuf
rpc Navigate(NavigateRequest) returns (NavigateResponse);
```

### Cookies

```protobuf
rpc GetCookies(GetCookiesRequest) returns (GetCookiesResponse);
rpc SetCookies(SetCookiesRequest) returns (SetCookiesResponse);
```

### JavaScript

```protobuf
rpc ExecuteJS(ExecuteJSRequest) returns (ExecuteJSResponse);
```

### Proxy

```protobuf
rpc SetProxy(SetProxyRequest) returns (SetProxyResponse);
```

### Signatures

```protobuf
rpc ExecuteSignature(ExecuteSignatureRequest) returns (ExecuteSignatureResponse);
```

## Python Integration

The Python crawler will call this service via gRPC:

```python
import grpc
from proto import browser_pb2, browser_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = browser_pb2_grpc.BrowserServiceStub(channel)

# Create browser
stub.CreateBrowser(browser_pb2.CreateBrowserRequest(
    browser_id="crawler_1",
    headless=True
))

# Navigate
stub.Navigate(browser_pb2.NavigateRequest(
    browser_id="crawler_1",
    url="https://example.com"
))

# Get cookies
response = stub.GetCookies(browser_pb2.GetCookiesRequest(
    browser_id="crawler_1",
    url="https://example.com"
))
```

## Development Status

- [x] Phase 0: Energy framework validation (energy-spike/)
- [x] Phase 1.1: Directory structure and scaffolding
- [ ] Phase 1.2: Protocol Buffers completion
- [ ] Phase 1.3: Energy integration (browser lifecycle, navigation, cookies)
- [ ] Phase 1.4: Signature execution
- [ ] Phase 1.5: Python client integration

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `:50051` | gRPC server listen address |

## Related

- [EnergyCrawler](../) - Main crawler project
- [Energy Framework](https://github.com/energye/energy) - CEF Go bindings
- [energy-spike](../energy-spike/) - Phase 0 validation code
