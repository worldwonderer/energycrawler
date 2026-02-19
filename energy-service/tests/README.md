# Energy Service Tests

## Running Tests

```bash
# Run all tests
go test ./... -v

# Run specific test file
go test -run TestManagerBasics ./...

# Run with coverage
go test -cover ./...

# Run with race detection
go test -race ./...
```

## Test Files

- `setup_test.go` - Test server setup and utilities
- `manager_test.go` - Browser manager unit tests
- `mocks/mock_browser.go` - Mock browser implementations for testing
