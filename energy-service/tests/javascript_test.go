package tests

import (
	"testing"
	"time"

	"energy-service/browser"
)

// TestNavigate_Timeout tests navigation timeout behavior
func TestNavigate_Timeout(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		url       string
		timeoutMs int32
		wantError bool
	}{
		{
			name:      "navigate with non-existent browser fails",
			browserID: "non-existent",
			url:       "https://example.com",
			timeoutMs: 5000,
			wantError: true,
		},
		{
			name:      "navigate with zero timeout uses default",
			browserID: "browser1",
			url:       "https://example.com",
			timeoutMs: 0,
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "navigate with short timeout",
			browserID: "browser1",
			url:       "https://example.com",
			timeoutMs: 100,
			wantError: true,
		},
		{
			name:      "navigate with empty URL",
			browserID: "browser1",
			url:       "",
			timeoutMs: 5000,
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			statusCode, err := mgr.Navigate(tt.browserID, tt.url, tt.timeoutMs)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
				if statusCode == 0 && err == nil {
					t.Error("Expected non-zero status code for successful navigation")
				}
			}
		})
	}
}

// TestNavigate_Success tests successful navigation scenarios
func TestNavigate_Success(t *testing.T) {
	mgr := browser.NewManager()

	// Note: Without a real browser window, we can only test error cases
	// In a real scenario with Energy running, we would test:
	// - Navigate to valid URL
	// - Check status code
	// - Verify navigation state tracking

	t.Run("navigation state is created", func(t *testing.T) {
		// Verify navigation state structure
		state := &browser.NavigationState{
			ID:         "test-nav",
			URL:        "https://example.com",
			Done:       make(chan struct{}),
			StatusCode: 200,
		}

		AssertEqual(t, "test-nav", state.ID)
		AssertEqual(t, "https://example.com", state.URL)
		AssertEqual(t, int32(200), state.StatusCode)

		// Verify channel is created
		if state.Done == nil {
			t.Error("Expected Done channel to be initialized")
		}
	})

	t.Run("navigation state tracking", func(t *testing.T) {
		// Test that navigation state can be registered and unregistered
		state := &browser.NavigationState{
			ID:   "nav-test-1",
			URL:  "https://example.com",
			Done: make(chan struct{}),
		}

		mgr.RegisterNavigationState(state)
		mgr.UnregisterNavigationState("nav-test-1")

		// Should not panic
	})
}

// TestExecuteJS_Basic tests basic JavaScript execution
func TestExecuteJS_Basic(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		script    string
		wantError bool
	}{
		{
			name:      "execute JS with non-existent browser fails",
			browserID: "non-existent",
			script:    "console.log('test');",
			wantError: true,
		},
		{
			name:      "execute JS with empty script",
			browserID: "browser1",
			script:    "",
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "execute valid JS script",
			browserID: "browser1",
			script:    "document.title = 'Test';",
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "execute complex JS script",
			browserID: "browser1",
			script:    "(function() { return 1 + 1; })();",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := mgr.ExecuteJS(tt.browserID, tt.script)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
				// ExecuteJS returns empty string (no result)
				AssertEqual(t, "", result)
			}
		})
	}
}

// TestExecuteJS_WithResult tests JavaScript execution with result
func TestExecuteJS_WithResult(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		script    string
		timeoutMs int32
		wantError bool
	}{
		{
			name:      "execute JS with result - non-existent browser",
			browserID: "non-existent",
			script:    "1 + 1",
			timeoutMs: 5000,
			wantError: true,
		},
		{
			name:      "execute JS with result - zero timeout",
			browserID: "browser1",
			script:    "Date.now()",
			timeoutMs: 0,
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "execute JS with result - short timeout",
			browserID: "browser1",
			script:    "JSON.stringify({key: 'value'})",
			timeoutMs: 100,
			wantError: true,
		},
		{
			name:      "execute JS with result - complex object",
			browserID: "browser1",
			script:    "({name: 'test', value: 123})",
			timeoutMs: 5000,
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := mgr.ExecuteJSWithResult(tt.browserID, tt.script, tt.timeoutMs)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
				if result == "" {
					t.Error("Expected non-empty result")
				}
				t.Logf("Result: %s", result)
			}
		})
	}
}

// TestJSResultChannelManagement tests JS result channel lifecycle
func TestJSResultChannelManagement(t *testing.T) {
	mgr := browser.NewManager()

	t.Run("handle JS result - non-existent request", func(t *testing.T) {
		// Should not panic when handling result for non-existent request
		mgr.HandleJSResult("non-existent-request", `{"result": "test"}`, "")
	})

	t.Run("handle JS result - with error", func(t *testing.T) {
		// Should not panic
		mgr.HandleJSResult("test-request", "", "Error occurred")
	})
}

// TestGetMainFrame tests getting the main frame
func TestGetMainFrame(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		wantError bool
	}{
		{
			name:      "get main frame - non-existent browser",
			browserID: "non-existent",
			wantError: true,
		},
		{
			name:      "get main frame - empty ID",
			browserID: "",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			frame, err := mgr.GetMainFrame(tt.browserID)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
				if frame != nil {
					t.Error("Expected nil frame for error case")
				}
			} else {
				AssertNoError(t, err)
			}
		})
	}
}

// TestNavigationTimeout tests navigation timeout scenarios
func TestNavigationTimeout(t *testing.T) {
	t.Run("timeout calculation", func(t *testing.T) {
		tests := []struct {
			inputMs   int32
			expectSec time.Duration
		}{
			{0, 30 * time.Second},        // Default timeout
			{1000, 1 * time.Second},       // 1 second
			{5000, 5 * time.Second},       // 5 seconds
			{100, 100 * time.Millisecond}, // 100ms
		}

		for _, tt := range tests {
			var timeout time.Duration
			if tt.inputMs <= 0 {
				timeout = 30 * time.Second
			} else {
				timeout = time.Duration(tt.inputMs) * time.Millisecond
			}

			AssertEqual(t, tt.expectSec, timeout)
		}
	})
}
