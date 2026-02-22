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
# Start with macOS launcher
bash start-macos.sh
```

```bash
# Recommended: guarded start + auto-restart from project root
bash scripts/ensure_energy_service.sh
```

```bash
# Health check from project root
uv run python scripts/energy_service_healthcheck.py --host localhost --port 50051
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

This module is actively used by EnergyCrawler and maintained in this repository.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GRPC_PORT` | `:50051` | gRPC server listen address |

## Related

- [EnergyCrawler](../) - Main crawler project
- [Energy Framework](https://github.com/energye/energy) - CEF Go bindings
