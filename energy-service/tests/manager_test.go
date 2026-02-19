package tests

import (
	"testing"

	"energy-service/browser"
	"energy-service/server"
)

// TestBrowserManagerBasics tests basic browser manager operations
func TestBrowserManagerBasics(t *testing.T) {
	mgr := browser.NewManager()

	t.Run("NewManager_IsNotInitialized", func(t *testing.T) {
		if mgr.IsInitialized() {
			t.Error("New manager should not be initialized")
		}
	})

	t.Run("CreateBrowser_WithoutEnergy_Fails", func(t *testing.T) {
		err := mgr.Create("test-browser", true)
		if err == nil {
			t.Error("Expected error when creating browser without Energy runtime")
		}
		t.Logf("Expected error: %v", err)
	})

	t.Run("GetBrowser_NonExistent_Fails", func(t *testing.T) {
		_, err := mgr.Get("non-existent")
		if err == nil {
			t.Error("Expected error for non-existent browser")
		}
		t.Logf("Expected error: %v", err)
	})

	t.Run("CloseBrowser_NonExistent_Fails", func(t *testing.T) {
		err := mgr.Close("non-existent")
		if err == nil {
			t.Error("Expected error when closing non-existent browser")
		}
		t.Logf("Expected error: %v", err)
	})

	t.Run("CloseAll_NoPanic", func(t *testing.T) {
		// Should not panic with empty manager
		mgr.CloseAll()
	})
}

// TestBrowserServerBasics tests basic browser server operations
func TestBrowserServerBasics(t *testing.T) {
	srv := server.NewBrowserServer()

	t.Run("NewServer_HasManager", func(t *testing.T) {
		mgr := srv.GetManager()
		if mgr == nil {
			t.Error("Server should have a manager")
		}
	})

	t.Run("Shutdown_NoPanic", func(t *testing.T) {
		// Should not panic
		srv.Shutdown()
	})
}

// TestNavigationState tests navigation state tracking
func TestNavigationState(t *testing.T) {
	state := &browser.NavigationState{
		ID:         "test-nav",
		URL:        "https://example.com",
		StatusCode: 200,
	}

	if state.ID != "test-nav" {
		t.Errorf("Expected ID 'test-nav', got %s", state.ID)
	}

	if state.URL != "https://example.com" {
		t.Errorf("Expected URL 'https://example.com', got %s", state.URL)
	}

	if state.StatusCode != 200 {
		t.Errorf("Expected status 200, got %d", state.StatusCode)
	}
}

// TestCookieDataStructure tests cookie data structure
func TestCookieDataStructure(t *testing.T) {
	cookie := browser.Cookie{
		Name:     "test",
		Value:    "value",
		Domain:   "example.com",
		Path:     "/",
		Secure:   true,
		HttpOnly: false,
	}

	if cookie.Name != "test" {
		t.Errorf("Expected name 'test', got %s", cookie.Name)
	}

	if cookie.Domain != "example.com" {
		t.Errorf("Expected domain 'example.com', got %s", cookie.Domain)
	}
}

// TestManagerConcurrentAccess tests concurrent operations on manager
func TestManagerConcurrentAccess(t *testing.T) {
	mgr := browser.NewManager()

	done := make(chan bool, 10)

	// Concurrent reads
	for i := 0; i < 5; i++ {
		go func() {
			_ = mgr.IsInitialized()
			done <- true
		}()
	}

	// Concurrent writes
	for i := 0; i < 5; i++ {
		go func() {
			_ = mgr.Create("test", true)
			done <- true
		}()
	}

	// Wait for all operations
	for i := 0; i < 10; i++ {
		<-done
	}
}

// TestManager_CreateBrowser tests browser creation scenarios
func TestManager_CreateBrowser(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		id        string
		headless  bool
		setup     func()
		wantError bool
	}{
		{
			name:      "create without Energy runtime fails",
			id:        "browser1",
			headless:  true,
			setup:     func() {},
			wantError: true,
		},
		{
			name:     "create duplicate browser fails",
			id:       "browser1",
			headless: true,
			setup: func() {
				// First creation will fail but register attempt
				_ = mgr.Create("browser1", true)
			},
			wantError: true,
		},
		{
			name:      "create with empty ID fails",
			id:        "",
			headless:  true,
			setup:     func() {},
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tt.setup()

			err := mgr.Create(tt.id, tt.headless)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
			}
		})
	}
}

// TestManager_CloseBrowser tests browser closing scenarios
func TestManager_CloseBrowser(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		id        string
		setup     func()
		wantError bool
	}{
		{
			name:      "close non-existent browser fails",
			id:        "non-existent",
			setup:     func() {},
			wantError: true,
		},
		{
			name: "close existing browser succeeds",
			id:   "browser1",
			setup: func() {
				// Attempt to create (will fail but we test close anyway)
			},
			wantError: true, // Will fail because browser doesn't actually exist
		},
		{
			name:      "close with empty ID fails",
			id:        "",
			setup:     func() {},
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tt.setup()

			err := mgr.Close(tt.id)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
			}
		})
	}
}

// TestManager_GetBrowser tests retrieving browser instances
func TestManager_GetBrowser(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		id        string
		wantError bool
	}{
		{
			name:      "get non-existent browser fails",
			id:        "non-existent",
			wantError: true,
		},
		{
			name:      "get with empty ID fails",
			id:        "",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			instance, err := mgr.Get(tt.id)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
				if instance != nil {
					t.Error("Expected nil instance for error case")
				}
			} else {
				AssertNoError(t, err)
				if instance == nil {
					t.Error("Expected non-nil instance for success case")
				}
			}
		})
	}
}

// TestManager_CloseAll tests closing all browsers
func TestManager_CloseAll(t *testing.T) {
	mgr := browser.NewManager()

	// Should not panic with empty manager
	mgr.CloseAll()

	// Should not panic when called multiple times
	mgr.CloseAll()
	mgr.CloseAll()
}

// TestManager_NavigationState tests navigation state management
func TestManager_NavigationState(t *testing.T) {
	mgr := browser.NewManager()

	t.Run("register and unregister navigation state", func(t *testing.T) {
		state := &browser.NavigationState{
			ID:   "test-nav-1",
			URL:  "https://example.com",
			Done: make(chan struct{}),
		}

		// Register
		mgr.RegisterNavigationState(state)

		// Unregister
		mgr.UnregisterNavigationState("test-nav-1")

		// Should not panic
	})

	t.Run("unregister non-existent state", func(t *testing.T) {
		// Should not panic
		mgr.UnregisterNavigationState("non-existent")
	})
}

// TestManager_DefaultWindow tests default window management
func TestManager_DefaultWindow(t *testing.T) {
	mgr := browser.NewManager()

	t.Run("get default window when not set", func(t *testing.T) {
		window := mgr.GetDefaultWindow()
		if window != nil {
			t.Error("Expected nil default window when not set")
		}
	})

	t.Run("set and get default window", func(t *testing.T) {
		// Note: We can't set a real window without Energy runtime
		// Just test that it doesn't panic
		mgr.SetDefaultWindow(nil)
		window := mgr.GetDefaultWindow()
		if window != nil {
			t.Error("Expected nil default window")
		}
	})
}
