package browser

import (
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/energye/energy/v2/cef"
	"github.com/energye/energy/v2/consts"
	"github.com/energye/golcl/lcl"
)

// Cookie represents an HTTP cookie
type Cookie struct {
	Name     string
	Value    string
	Domain   string
	Path     string
	Secure   bool
	HttpOnly bool
}

// CookieRequest tracks a cookie request
type CookieRequest struct {
	ID      int32
	URL     string
	Done    chan struct{}
	Cookies []Cookie
	Error   error
	mu      sync.RWMutex
}

// GetCookies retrieves cookies from a browser instance
func (m *Manager) GetCookies(id string, url string) ([]Cookie, error) {
	instance, err := m.Get(id)
	if err != nil {
		return nil, err
	}

	instance.mu.RLock()
	defer instance.mu.RUnlock()

	if instance.Window == nil {
		return nil, fmt.Errorf("browser window not initialized: %s", id)
	}

	// Clear previous cookie results for ID 1
	m.cookieResultsMu.Lock()
	m.cookieResults[1] = nil
	m.cookieResultsMu.Unlock()

	// Create a request tracker
	req := &CookieRequest{
		ID:      1,
		URL:     url,
		Done:    make(chan struct{}),
		Cookies: []Cookie{},
	}

	// Get window info to access chromium
	chromium := instance.Window.Chromium()
	if chromium == nil {
		return nil, fmt.Errorf("chromium not available: %s", id)
	}

	// Visit cookies for the URL
	// The ID parameter (1) is used to track the request
	chromium.VisitURLCookies(url, true, 1)

	// Wait for cookie collection with timeout
	// Cookie visitor will populate m.cookieResults[1] via the callback
	select {
	case <-req.Done:
		m.cookieResultsMu.RLock()
		cookies := m.cookieResults[1]
		m.cookieResultsMu.RUnlock()
		return cookies, nil
	case <-time.After(10 * time.Second):
		// Timeout - return whatever we have collected
		m.cookieResultsMu.RLock()
		cookies := m.cookieResults[1]
		m.cookieResultsMu.RUnlock()
		if len(cookies) == 0 {
			return nil, fmt.Errorf("cookie retrieval timeout")
		}
		return cookies, nil
	}
}

// SetCookies sets cookies in a browser instance
func (m *Manager) SetCookies(id string, cookies []Cookie) error {
	instance, err := m.Get(id)
	if err != nil {
		return err
	}

	instance.mu.RLock()
	defer instance.mu.RUnlock()

	if instance.Window == nil {
		return fmt.Errorf("browser window not initialized: %s", id)
	}

	chromium := instance.Window.Chromium()
	if chromium == nil {
		return fmt.Errorf("chromium not available: %s", id)
	}

	var setErr error
	cef.QueueSyncCall(func(_ int) {
		// Set each cookie on the UI thread.
		// CEF expects a valid URL host (without leading dot), while cookie Domain
		// may legitimately start with ".".
		for i, c := range cookies {
			domain := strings.TrimSpace(c.Domain)
			if domain == "" {
				setErr = fmt.Errorf("cookie domain is required for cookie %q", c.Name)
				return
			}
			host := strings.TrimPrefix(domain, ".")
			if host == "" {
				setErr = fmt.Errorf("invalid cookie domain %q for cookie %q", c.Domain, c.Name)
				return
			}
			path := strings.TrimSpace(c.Path)
			if path == "" {
				path = "/"
			}
			cookieURL := "https://" + host + "/"
			now := time.Now()
			chromium.SetCookie(
				cookieURL,                 // URL
				c.Name,                    // Name
				c.Value,                   // Value
				domain,                    // Domain
				path,                      // Path
				c.Secure,                  // Secure
				c.HttpOnly,                // HttpOnly
				true,                      // Has Expires
				now,                       // Creation
				now,                       // Last Access
				now.Add(365*24*time.Hour), // Expires
				consts.Ccss_CEF_COOKIE_SAME_SITE_UNSPECIFIED, // SameSite
				consts.CEF_COOKIE_PRIORITY_MEDIUM,            // Priority
				true,                                         // SetImmediately
				int32(i+1),                                   // ID
			)
		}

		// Force write-through to avoid races where immediate read misses new cookies.
		chromium.FlushCookieStore(true)
	})
	if setErr != nil {
		return setErr
	}
	return nil
}

// DeleteCookies deletes cookies for a URL
func (m *Manager) DeleteCookies(id string, url string, cookieName string) error {
	instance, err := m.Get(id)
	if err != nil {
		return err
	}

	instance.mu.RLock()
	defer instance.mu.RUnlock()

	if instance.Window == nil {
		return fmt.Errorf("browser window not initialized: %s", id)
	}

	chromium := instance.Window.Chromium()
	if chromium == nil {
		return fmt.Errorf("chromium not available: %s", id)
	}

	// Delete cookies matching URL and name
	// If cookieName is empty, all cookies for the URL are deleted
	chromium.DeleteCookies(url, cookieName, false)

	return nil
}

// GetAllCookies retrieves all cookies from a browser instance
func (m *Manager) GetAllCookies(id string) ([]Cookie, error) {
	instance, err := m.Get(id)
	if err != nil {
		return nil, err
	}

	instance.mu.RLock()
	defer instance.mu.RUnlock()

	if instance.Window == nil {
		return nil, fmt.Errorf("browser window not initialized: %s", id)
	}

	// Clear previous cookie results for ID 2 (using different ID for all cookies)
	m.cookieResultsMu.Lock()
	m.cookieResults[2] = nil
	m.cookieResultsMu.Unlock()

	chromium := instance.Window.Chromium()
	if chromium == nil {
		return nil, fmt.Errorf("chromium not available: %s", id)
	}

	// Visit all cookies
	chromium.VisitAllCookies(2)

	// Wait for cookie collection with timeout
	select {
	case <-time.After(10 * time.Second):
		m.cookieResultsMu.RLock()
		cookies := m.cookieResults[2]
		m.cookieResultsMu.RUnlock()
		if len(cookies) == 0 {
			return nil, fmt.Errorf("cookie retrieval timeout")
		}
		return cookies, nil
	}
}

// SetupCookieEventCallbacks sets up cookie event callbacks on a BrowserEvent
// This should be called in the SetBrowserInit callback
// Note: This is now handled by Manager.SetupCookieCallbacks
func SetupCookieEventCallbacks(event *cef.BrowserEvent, manager *Manager) {
	event.SetOnCookiesVisited(func(sender lcl.IObject, cookie *cef.TCefCookie, deleteCookie, result *bool) {
		if cookie == nil {
			return
		}

		manager.cookieResultsMu.Lock()
		// Use ID 1 as default
		if manager.cookieResults[1] == nil {
			manager.cookieResults[1] = []Cookie{}
		}
		manager.cookieResults[1] = append(manager.cookieResults[1], Cookie{
			Name:     cookie.Name,
			Value:    cookie.Value,
			Domain:   cookie.Domain,
			Path:     cookie.Path,
			Secure:   cookie.Secure,
			HttpOnly: cookie.Httponly,
		})
		manager.cookieResultsMu.Unlock()
	})

	event.SetOnCookiesDeleted(func(sender lcl.IObject, numDeleted int32) {
		// Can be used to track cookie deletion
	})

	event.SetOnCookieSet(func(sender lcl.IObject, success bool, ID int32) {
		// Can be used to track cookie setting
	})

	event.SetOnCookieVisitorDestroyed(func(sender lcl.IObject, ID int32) {
		// Cookie visitor is done - could signal completion here
	})
}
