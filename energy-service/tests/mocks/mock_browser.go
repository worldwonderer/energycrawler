package mocks

import (
	"github.com/energye/energy/v2/cef"
)

// MockBrowserWindow is a minimal mock for testing browser operations
// without requiring the full Energy runtime.
type MockBrowserWindow struct {
	id         int32
	currentURL string
}

// NewMockBrowserWindow creates a new mock browser window
func NewMockBrowserWindow() *MockBrowserWindow {
	return &MockBrowserWindow{
		id: 1,
	}
}

// ID returns the mock browser ID
func (m *MockBrowserWindow) ID() int32 {
	return m.id
}

// SetCurrentURL sets the current URL
func (m *MockBrowserWindow) SetCurrentURL(url string) {
	m.currentURL = url
}

// GetCurrentURL returns the current URL
func (m *MockBrowserWindow) GetCurrentURL() string {
	return m.currentURL
}

// MockCookie represents a mock cookie for testing
type MockCookie struct {
	Name     string
	Value    string
	Domain   string
	Path     string
	Secure   bool
	HttpOnly bool
}

// NewMockCookie creates a new mock cookie
func NewMockCookie(name, value, domain string) *MockCookie {
	return &MockCookie{
		Name:   name,
		Value:  value,
		Domain: domain,
		Path:   "/",
	}
}

// ToCefCookie converts mock cookie to CEF cookie format
func (m *MockCookie) ToCefCookie() *cef.TCefCookie {
	return &cef.TCefCookie{
		Name:     m.Name,
		Value:    m.Value,
		Domain:   m.Domain,
		Path:     m.Path,
		Secure:   m.Secure,
		Httponly: m.HttpOnly,
	}
}

// MockNavigationResult represents a mock navigation result
type MockNavigationResult struct {
	StatusCode int32
	Error      error
	URL        string
}

// NewMockNavigationResult creates a new mock navigation result
func NewMockNavigationResult(statusCode int32, url string) *MockNavigationResult {
	return &MockNavigationResult{
		StatusCode: statusCode,
		URL:        url,
	}
}
