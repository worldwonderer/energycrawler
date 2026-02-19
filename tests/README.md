# Test Infrastructure

This document describes the test infrastructure for the EnergyCrawler Energy project.

## Directory Structure

```
EnergyCrawler/
├── energy-service/           # Go Energy browser service
│   └── tests/
│       ├── setup_test.go     # Test initialization and utilities
│       ├── manager_test.go   # Manager unit tests
│       └── mocks/
│           └── mock_browser.go # Mock browser implementations
│
├── energy_client/            # Python gRPC client
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py       # pytest fixtures
│       ├── test_client.py    # Client unit tests
│       └── test_interface.py # Interface tests
│
└── tests/
    └── e2e/
        ├── __init__.py
        ├── conftest.py       # E2E fixtures (starts Go service)
        ├── test_basic_flow.py # Basic flow tests
        ├── test_signature.py # Signature and error tests
        └── run_e2e.sh        # E2E test runner script
```

## Running Tests

### Go Unit Tests

```bash
cd energy-service
go test ./... -v
```

### Python Unit Tests

```bash
cd energy_client
pip install pytest grpcio grpcio-tools
pytest tests/ -v
```

### E2E Tests

The E2E tests require the Energy service to be running.

**Option 1: Using the runner script (recommended)**

```bash
cd tests/e2e
./run_e2e.sh
```

**Option 2: Manual execution**

```bash
# Terminal 1: Start the service
cd energy-service
go build -o energy-service .
./energy-service

# Terminal 2: Run tests
cd tests/e2e
pytest -v -m e2e
```

### Real Crawl Flow (XHS + X, with login gate)

For real crawler verification, use the interactive flow runner. It will:
1. check Energy service connectivity
2. detect XHS/X login status
3. open login pages and pause until login is complete
4. run real XHS/X crawling

```bash
cd /Users/pite/energycrawler
.venv/bin/python tests/e2e/run_xhs_x_crawl_flow.py
```

Runner defaults are conservative for account safety:
- `--max-count` default is `3`
- comment limit is capped to `3` per note
- per-batch/request interval is at least `10s`

For the safest real check, run with a single item:

```bash
cd /Users/pite/energycrawler
.venv/bin/python tests/e2e/run_xhs_x_crawl_flow.py --max-count 1
```

Only perform login checks (skip crawl):

```bash
cd /Users/pite/energycrawler
.venv/bin/python tests/e2e/run_xhs_x_crawl_flow.py --skip-crawl
```

If X login via Google is blocked in embedded browser, set cookie envs and skip interactive X login:

```bash
export TWITTER_AUTH_TOKEN="your_auth_token"
export TWITTER_CT0="your_ct0"
.venv/bin/python tests/e2e/run_xhs_x_crawl_flow.py
```

### Run All Tests

```bash
cd tests/e2e
./run_e2e.sh all
```

## Test Categories

### Unit Tests (Go)

- `setup_test.go`: Test utilities and mock server setup
- `manager_test.go`: Browser manager operations

### Unit Tests (Python)

- `test_client.py`: BrowserClient API tests
- `test_interface.py`: BrowserInterface abstraction tests

### E2E Tests

- `test_basic_flow.py`: Browser lifecycle, navigation, cookies, JS execution
- `test_signature.py`: Signature generation, proxy settings, error handling

## Test Markers

Python tests use markers to categorize tests:

- `@pytest.mark.e2e`: End-to-end tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.slow`: Slow running tests
- `@pytest.mark.requires_energy`: Tests requiring Energy runtime

Run specific markers:

```bash
pytest -m e2e           # Run only E2E tests
pytest -m "not slow"    # Skip slow tests
```

## Configuration

### Environment Variables

- `ENERGY_SERVICE_HOST`: Service hostname (default: localhost)
- `ENERGY_SERVICE_PORT`: Service port (default: 50051)
- `ENERGY_SERVICE_PATH`: Path to energy-service directory
- `ENERGY_SERVICE_BINARY`: Path to energy-service binary
- `SERVICE_STARTUP_TIMEOUT`: Timeout for service startup (default: 30s)

### pytest Configuration

Configuration is in `energy_client/pyproject.toml`:

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
```

## Writing New Tests

### Go Tests

1. Create test files with `_test.go` suffix
2. Use `TestServer` from `setup_test.go` for gRPC testing
3. Run with `go test ./...`

### Python Tests

1. Create test files with `test_*.py` prefix
2. Use fixtures from `conftest.py`
3. Add appropriate markers

### E2E Tests

1. Add tests to `tests/e2e/test_*.py`
2. Use `browser_client` or `browser_backend` fixtures
3. Always cleanup browsers in `finally` blocks
4. Use `test_browser_id` fixture for unique IDs

## Troubleshooting

### Service Won't Start

- Check if port 50051 is already in use: `lsof -i :50051`
- Check Energy dependencies are installed

### Import Errors

- Ensure `energy_client` is in Python path
- Install dependencies: `pip install grpcio grpcio-tools protobuf`

### E2E Tests Timeout

- Increase `SERVICE_STARTUP_TIMEOUT` environment variable
- Check system resources (CEF requires significant memory)
