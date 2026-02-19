package tests

import (
	"testing"

	"energy-service/browser"
)

// TestGetCookies_Empty tests getting cookies when none exist
func TestGetCookies_Empty(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		url       string
		wantError bool
	}{
		{
			name:      "get cookies - non-existent browser",
			browserID: "non-existent",
			url:       "https://example.com",
			wantError: true,
		},
		{
			name:      "get cookies - empty URL",
			browserID: "browser1",
			url:       "",
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "get cookies - valid URL, no browser",
			browserID: "browser1",
			url:       "https://www.example.com/path",
			wantError: true,
		},
		{
			name:      "get cookies - localhost URL",
			browserID: "browser1",
			url:       "http://localhost:8080",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cookies, err := mgr.GetCookies(tt.browserID, tt.url)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
				if len(cookies) > 0 {
					t.Error("Expected empty cookies slice for error case")
				}
			} else {
				AssertNoError(t, err)
				// Empty cookies is valid when none exist
				t.Logf("Retrieved %d cookies", len(cookies))
			}
		})
	}
}

// TestSetCookies_Basic tests setting cookies
func TestSetCookies_Basic(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		cookies   []browser.Cookie
		wantError bool
	}{
		{
			name:      "set cookies - non-existent browser",
			browserID: "non-existent",
			cookies: []browser.Cookie{
				{Name: "test", Value: "value", Domain: "example.com"},
			},
			wantError: true,
		},
		{
			name:      "set cookies - empty slice",
			browserID: "browser1",
			cookies:   []browser.Cookie{},
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "set cookies - single cookie",
			browserID: "browser1",
			cookies: []browser.Cookie{
				{
					Name:     "session",
					Value:    "abc123",
					Domain:   "example.com",
					Path:     "/",
					Secure:   true,
					HttpOnly: true,
				},
			},
			wantError: true,
		},
		{
			name:      "set cookies - multiple cookies",
			browserID: "browser1",
			cookies: []browser.Cookie{
				{Name: "cookie1", Value: "value1", Domain: "example.com"},
				{Name: "cookie2", Value: "value2", Domain: "example.com"},
				{Name: "cookie3", Value: "value3", Domain: "example.com"},
			},
			wantError: true,
		},
		{
			name:      "set cookies - with special characters",
			browserID: "browser1",
			cookies: []browser.Cookie{
				{
					Name:   "special",
					Value:  "value%20with%20spaces&symbols=value",
					Domain: "example.com",
				},
			},
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := mgr.SetCookies(tt.browserID, tt.cookies)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
			}
		})
	}
}

// TestCookieStruct tests cookie data structure
func TestCookieStruct(t *testing.T) {
	tests := []struct {
		name     string
		cookie   browser.Cookie
		expected browser.Cookie
	}{
		{
			name: "basic cookie",
			cookie: browser.Cookie{
				Name:   "test",
				Value:  "value",
				Domain: "example.com",
			},
			expected: browser.Cookie{
				Name:   "test",
				Value:  "value",
				Domain: "example.com",
			},
		},
		{
			name: "secure cookie",
			cookie: browser.Cookie{
				Name:     "secure",
				Value:    "secret",
				Domain:   "example.com",
				Path:     "/secure",
				Secure:   true,
				HttpOnly: true,
			},
			expected: browser.Cookie{
				Name:     "secure",
				Value:    "secret",
				Domain:   "example.com",
				Path:     "/secure",
				Secure:   true,
				HttpOnly: true,
			},
		},
		{
			name: "cookie with path",
			cookie: browser.Cookie{
				Name:   "pathcookie",
				Value:  "value",
				Domain: "example.com",
				Path:   "/api/v1",
			},
			expected: browser.Cookie{
				Name:   "pathcookie",
				Value:  "value",
				Domain: "example.com",
				Path:   "/api/v1",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			AssertEqual(t, tt.expected.Name, tt.cookie.Name)
			AssertEqual(t, tt.expected.Value, tt.cookie.Value)
			AssertEqual(t, tt.expected.Domain, tt.cookie.Domain)
			AssertEqual(t, tt.expected.Path, tt.cookie.Path)
			AssertEqual(t, tt.expected.Secure, tt.cookie.Secure)
			AssertEqual(t, tt.expected.HttpOnly, tt.cookie.HttpOnly)
		})
	}
}

// TestDeleteCookies tests cookie deletion
func TestDeleteCookies(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name       string
		browserID  string
		url        string
		cookieName string
		wantError  bool
	}{
		{
			name:       "delete cookies - non-existent browser",
			browserID:  "non-existent",
			url:        "https://example.com",
			cookieName: "test",
			wantError:  true,
		},
		{
			name:       "delete cookies - specific cookie",
			browserID:  "browser1",
			url:        "https://example.com",
			cookieName: "session",
			wantError:  true, // Will fail because browser doesn't exist
		},
		{
			name:       "delete cookies - all cookies for URL",
			browserID:  "browser1",
			url:        "https://example.com",
			cookieName: "", // Empty name deletes all
			wantError:  true,
		},
		{
			name:       "delete cookies - empty URL",
			browserID:  "browser1",
			url:        "",
			cookieName: "test",
			wantError:  true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := mgr.DeleteCookies(tt.browserID, tt.url, tt.cookieName)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
			}
		})
	}
}

// TestGetAllCookies tests retrieving all cookies
func TestGetAllCookies(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		wantError bool
	}{
		{
			name:      "get all cookies - non-existent browser",
			browserID: "non-existent",
			wantError: true,
		},
		{
			name:      "get all cookies - valid browser",
			browserID: "browser1",
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "get all cookies - empty ID",
			browserID: "",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cookies, err := mgr.GetAllCookies(tt.browserID)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
				if len(cookies) > 0 {
					t.Error("Expected empty cookies slice for error case")
				}
			} else {
				AssertNoError(t, err)
				t.Logf("Retrieved %d cookies", len(cookies))
			}
		})
	}
}

// TestCookieRequest tests cookie request structure
func TestCookieRequest(t *testing.T) {
	t.Run("create cookie request", func(t *testing.T) {
		req := &browser.CookieRequest{
			ID:      1,
			URL:     "https://example.com",
			Done:    make(chan struct{}),
			Cookies: []browser.Cookie{},
		}

		AssertEqual(t, int32(1), req.ID)
		AssertEqual(t, "https://example.com", req.URL)

		if req.Done == nil {
			t.Error("Expected Done channel to be initialized")
		}

		if req.Cookies == nil {
			t.Error("Expected Cookies slice to be initialized")
		}
	})

	t.Run("cookie request with initial cookies", func(t *testing.T) {
		cookies := []browser.Cookie{
			{Name: "cookie1", Value: "value1", Domain: "example.com"},
			{Name: "cookie2", Value: "value2", Domain: "example.com"},
		}

		req := &browser.CookieRequest{
			ID:      2,
			URL:     "https://example.com",
			Cookies: cookies,
		}

		AssertEqual(t, 2, len(req.Cookies))
	})
}

// TestCookieValidation tests cookie validation scenarios
func TestCookieValidation(t *testing.T) {
	tests := []struct {
		name     string
		cookie   browser.Cookie
		isValid  bool
		reason   string
	}{
		{
			name: "valid cookie",
			cookie: browser.Cookie{
				Name:   "valid",
				Value:  "value",
				Domain: "example.com",
				Path:   "/",
			},
			isValid: true,
			reason:  "all required fields present",
		},
		{
			name: "cookie with empty name",
			cookie: browser.Cookie{
				Value:  "value",
				Domain: "example.com",
			},
			isValid: false,
			reason:  "name is empty",
		},
		{
			name: "cookie with empty domain",
			cookie: browser.Cookie{
				Name:  "test",
				Value: "value",
			},
			isValid: false,
			reason:  "domain is empty",
		},
		{
			name: "cookie with long value",
			cookie: browser.Cookie{
				Name:   "long",
				Value:  string(make([]byte, 4096)),
				Domain: "example.com",
			},
			isValid: true, // Long values are allowed
			reason:  "long values are valid",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Basic validation checks
			hasName := tt.cookie.Name != ""
			hasDomain := tt.cookie.Domain != ""

			isValid := hasName && hasDomain

			if isValid != tt.isValid {
				t.Errorf("Expected valid=%v, got valid=%v. Reason: %s",
					tt.isValid, isValid, tt.reason)
			}
		})
	}
}
