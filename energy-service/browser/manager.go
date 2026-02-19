package browser

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"strings"
	"sync"

	"github.com/energye/energy/v2/cef"
	"github.com/energye/energy/v2/consts"
	"github.com/energye/golcl/lcl"
)

// BrowserInstance represents a managed browser instance
type BrowserInstance struct {
	ID       string
	Headless bool
	Window   cef.IBrowserWindow
	mu       sync.RWMutex
}

// ClickResult represents the result of a click operation
type ClickResult struct {
	ElementFound bool
	ClickedX     int32
	ClickedY     int32
}

// Manager manages browser instances
type Manager struct {
	browsers   map[string]*BrowserInstance
	mu         sync.RWMutex
	app        *cef.TCEFApplication
	initialized bool

	// defaultWindow is the main browser window created by Energy
	defaultWindow cef.IBrowserWindow
	defaultWindowMu sync.RWMutex

	// Navigation state tracking
	navStates   map[string]*NavigationState
	navStatesMu sync.RWMutex

	// Cookie collection state
	cookieResults   map[int32][]Cookie
	cookieResultsMu sync.RWMutex
}

// NavigationState tracks the state of a navigation request
type NavigationState struct {
	ID         string
	URL        string
	Done       chan struct{}
	StatusCode int32
	Error      error
	closeOnce  sync.Once
}

// completeNavigation safely completes a navigation state with thread-safety
func (m *Manager) completeNavigation(state *NavigationState, statusCode int32, err error) {
	m.navStatesMu.Lock()
	if _, exists := m.navStates[state.ID]; exists {
		delete(m.navStates, state.ID)
		m.navStatesMu.Unlock()
		state.StatusCode = statusCode
		if err != nil {
			state.Error = err
		}
		state.closeOnce.Do(func() {
			close(state.Done)
		})
	} else {
		m.navStatesMu.Unlock()
	}
}

// NewManager creates a new browser manager
func NewManager() *Manager {
	return &Manager{
		browsers:     make(map[string]*BrowserInstance),
		navStates:    make(map[string]*NavigationState),
		cookieResults: make(map[int32][]Cookie),
	}
}

// SetDefaultWindow stores the main window created by Energy
func (m *Manager) SetDefaultWindow(window cef.IBrowserWindow) {
	m.defaultWindowMu.Lock()
	defer m.defaultWindowMu.Unlock()
	m.defaultWindow = window
	m.initialized = true
}

// GetDefaultWindow returns the main window
func (m *Manager) GetDefaultWindow() cef.IBrowserWindow {
	m.defaultWindowMu.RLock()
	defer m.defaultWindowMu.RUnlock()
	return m.defaultWindow
}

// urlMatches checks if a frame URL matches the target URL
// This handles cases like trailing slashes, scheme differences, etc.
func urlMatches(frameURL, targetURL string) bool {
	// Exact match
	if frameURL == targetURL {
		return true
	}

	// Handle empty target URL (matches any URL)
	if targetURL == "" {
		return true
	}

	// Normalize URLs for comparison - handle trailing slash differences
	normalizedFrame := strings.TrimSuffix(frameURL, "/")
	normalizedTarget := strings.TrimSuffix(targetURL, "/")

	return normalizedFrame == normalizedTarget
}

// SetupNavigationCallbacks sets up navigation event callbacks
func (m *Manager) SetupNavigationCallbacks(event *cef.BrowserEvent, window cef.IBrowserWindow) {
	log.Println("[Manager] Setting up navigation callbacks...")

	if window == nil {
		log.Println("[Manager] ERROR: window is nil!")
		return
	}

	chromium := window.Chromium()
	if chromium == nil {
		log.Println("[Manager] ERROR: chromium is nil!")
		return
	}

	log.Printf("[Manager] Chromium is valid: %v", chromium.IsValid())

	// Log all current navigation states for debugging
	m.navStatesMu.RLock()
	log.Printf("[Manager] Current navStates count: %d", len(m.navStates))
	for id, state := range m.navStates {
		log.Printf("[Manager]   - navState[%s]: URL=%s", id, state.URL)
	}
	m.navStatesMu.RUnlock()

	// Set up load start callback (Ex version with window parameter)
	event.SetOnLoadStart(func(sender lcl.IObject, browser *cef.ICefBrowser, frame *cef.ICefFrame, transitionType consts.TCefTransitionType, window cef.IBrowserWindow) {
		log.Printf("[Manager] OnLoadStart: url=%s, isMain=%v, transitionType=%v", frame.Url(), frame.IsMain(), transitionType)
	})

	// Set up loading state change callback (no window parameter)
	event.SetOnLoadingStateChange(func(sender lcl.IObject, browser *cef.ICefBrowser, isLoading, canGoBack, canGoForward bool) {
		log.Printf("[Manager] OnLoadingStateChange: isLoading=%v, canGoBack=%v, canGoForward=%v", isLoading, canGoBack, canGoForward)
		// Loading state changes are logged only
		// Page load completion is handled by OnLoadEnd
	})

	// Set up load error callback (no window parameter)
	event.SetOnLoadError(func(sender lcl.IObject, browser *cef.ICefBrowser, frame *cef.ICefFrame, errorCode consts.CEF_NET_ERROR, errorText string, failedUrl string) {
		log.Printf("[Manager] OnLoadError called: url=%s, error=%s, errorCode=%d", failedUrl, errorText, errorCode)

		if !frame.IsMain() {
			return
		}

		// ERR_ABORTED (usually -3) means loading was aborted (e.g., user navigated to another page)
		// For this case, we should not trigger an error as it may be normal behavior
		if errorCode == -3 { // ERR_ABORTED
			log.Printf("[Manager] Load aborted (ERR_ABORTED), ignoring...")
			return
		}

		// Find matching navigation states and collect them
		var matchedStates []*NavigationState
		m.navStatesMu.RLock()
		for _, state := range m.navStates {
			if urlMatches(failedUrl, state.URL) {
				matchedStates = append(matchedStates, state)
			}
		}
		m.navStatesMu.RUnlock()

		log.Printf("[Manager] OnLoadError: Found %d matching navigation states for failedUrl: %s", len(matchedStates), failedUrl)

		// Complete matched states using the helper method
		for _, state := range matchedStates {
			m.completeNavigation(state, int32(errorCode), errors.New(errorText))
		}
	})

	// Set up load end callback (Ex version with window parameter)
	event.SetOnLoadEnd(func(sender lcl.IObject, browser *cef.ICefBrowser, frame *cef.ICefFrame, httpStatusCode int32, window cef.IBrowserWindow) {
		frameURL := frame.Url()
		log.Printf("[Manager] OnLoadEnd called: url=%s, status=%d, isMain=%v", frameURL, httpStatusCode, frame.IsMain())

		if !frame.IsMain() {
			return // Only handle main frame
		}

		// Find matching navigation states and collect them
		var matchedStates []*NavigationState
		m.navStatesMu.RLock()
		for _, state := range m.navStates {
			log.Printf("[Manager] OnLoadEnd: Checking navState URL=%s against frameURL=%s, matches=%v", state.URL, frameURL, urlMatches(frameURL, state.URL))
			if urlMatches(frameURL, state.URL) {
				matchedStates = append(matchedStates, state)
			}
		}
		m.navStatesMu.RUnlock()

		log.Printf("[Manager] OnLoadEnd: Found %d matching navigation states for URL: %s", len(matchedStates), frameURL)

		// Complete matched states using the helper method
		for _, state := range matchedStates {
			m.completeNavigation(state, httpStatusCode, nil)
		}
	})
}

// SetupCookieCallbacks sets up cookie event callbacks
func (m *Manager) SetupCookieCallbacks(event *cef.BrowserEvent) {
	// SetOnCookiesVisited is called for each cookie when VisitURLCookies or VisitAllCookies is called
	// Note: The callback signature matches Energy v2 example - 4 parameters
	event.SetOnCookiesVisited(func(sender lcl.IObject, cookie *cef.TCefCookie, deleteCookie, result *bool) {
		if cookie == nil {
			return
		}

		log.Printf("[Cookie] Visited: %s = %s", cookie.Name, cookie.Value[:min(30, len(cookie.Value))])

		// Store the cookie
		m.cookieResultsMu.Lock()
		// Use ID 1 as default for single requests
		if m.cookieResults[1] == nil {
			m.cookieResults[1] = []Cookie{}
		}
		m.cookieResults[1] = append(m.cookieResults[1], Cookie{
			Name:     cookie.Name,
			Value:    cookie.Value,
			Domain:   cookie.Domain,
			Path:     cookie.Path,
			Secure:   cookie.Secure,
			HttpOnly: cookie.Httponly,
		})
		m.cookieResultsMu.Unlock()
	})

	event.SetOnCookieVisitorDestroyed(func(sender lcl.IObject, ID int32) {
		// Cookie visitor is done, results are collected
	})

	event.SetOnCookiesDeleted(func(sender lcl.IObject, numDeleted int32) {
		// Cookies deleted
	})

	event.SetOnCookieSet(func(sender lcl.IObject, success bool, ID int32) {
		// Cookie set result
	})
}

// Init initializes the Energy framework
// This must be called once before creating any browsers
func (m *Manager) Init() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.initialized {
		return nil
	}

	// Global initialization is done in main.go
	// The app is also created there
	m.initialized = true
	return nil
}

// Create creates a new browser instance
func (m *Manager) Create(id string, headless bool) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.browsers[id]; exists {
		return errors.New("browser instance already exists: " + id)
	}

	// Get the default window
	defaultWindow := m.GetDefaultWindow()
	if defaultWindow == nil {
		return errors.New("energy browser window not initialized - ensure Energy is running")
	}

	instance := &BrowserInstance{
		ID:       id,
		Headless: headless,
		Window:   defaultWindow, // Use the shared default window
	}

	m.browsers[id] = instance
	return nil
}

// CreateBrowserWindow creates the actual browser window for an instance
// This should be called within the Energy event loop context
func (m *Manager) CreateBrowserWindow(id string, url string) error {
	m.mu.RLock()
	instance, exists := m.browsers[id]
	m.mu.RUnlock()

	if !exists {
		return errors.New("browser instance not found: " + id)
	}

	instance.mu.Lock()
	defer instance.mu.Unlock()

	if instance.Window != nil {
		return errors.New("browser window already created: " + id)
	}

	// Use the default window
	instance.Window = m.GetDefaultWindow()
	if instance.Window == nil {
		return errors.New("no default window available")
	}

	// Navigate to the URL
	instance.Window.Chromium().LoadUrl(url)
	return nil
}

// Close closes a browser instance
func (m *Manager) Close(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	instance, exists := m.browsers[id]
	if !exists {
		return errors.New("browser instance not found: " + id)
	}

	// For shared window mode, we don't close the window
	// Just remove from the map
	instance.Window = nil
	delete(m.browsers, id)
	return nil
}

// CloseAll closes all browser instances
func (m *Manager) CloseAll() {
	m.mu.Lock()
	defer m.mu.Unlock()

	for id := range m.browsers {
		delete(m.browsers, id)
	}
}

// Get retrieves a browser instance
func (m *Manager) Get(id string) (*BrowserInstance, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	instance, exists := m.browsers[id]
	if !exists {
		return nil, errors.New("browser instance not found: " + id)
	}
	return instance, nil
}

// GetWindow retrieves the browser window for an instance
func (m *Manager) GetWindow(id string) (cef.IBrowserWindow, error) {
	instance, err := m.Get(id)
	if err != nil {
		return nil, err
	}

	instance.mu.RLock()
	defer instance.mu.RUnlock()

	if instance.Window == nil {
		return nil, errors.New("browser window not initialized: " + id)
	}

	return instance.Window, nil
}

// SetWindow sets the browser window for an instance
// This is used when the window is created via Energy callbacks
func (m *Manager) SetWindow(id string, window cef.IBrowserWindow) error {
	m.mu.RLock()
	instance, exists := m.browsers[id]
	m.mu.RUnlock()

	if !exists {
		return errors.New("browser instance not found: " + id)
	}

	instance.mu.Lock()
	defer instance.mu.Unlock()

	instance.Window = window
	return nil
}

// GetApp returns the Energy application instance
func (m *Manager) GetApp() *cef.TCEFApplication {
	return m.app
}

// IsInitialized returns whether the manager has been initialized
func (m *Manager) IsInitialized() bool {
	return m.initialized
}

// RegisterNavigationState registers a navigation state for tracking
func (m *Manager) RegisterNavigationState(state *NavigationState) {
	m.navStatesMu.Lock()
	m.navStates[state.ID] = state
	m.navStatesMu.Unlock()
}

// UnregisterNavigationState removes a navigation state
func (m *Manager) UnregisterNavigationState(id string) {
	m.navStatesMu.Lock()
	delete(m.navStates, id)
	m.navStatesMu.Unlock()
}


// Click clicks on an element specified by CSS selector or coordinates
// Uses real CEF mouse events (SendMouseClickEvent) which work with React/JavaScript frameworks
func (m *Manager) Click(id string, selector string, x, y int32, timeoutMs int32) (*ClickResult, error) {
	window, err := m.GetWindow(id)
	if err != nil {
		return nil, err
	}

	if window == nil {
		return nil, errors.New("browser window is nil")
	}

	chromium := window.Chromium()
	if chromium == nil {
		return nil, errors.New("chromium is nil")
	}

	var result ClickResult
	var clickX, clickY int32

	if selector != "" {
		// Find element position using JS, then click using CEF events
		script := fmt.Sprintf(`
(function() {
	var selector = %q;
	var element = document.querySelector(selector);
	if (element) {
		var rect = element.getBoundingClientRect();
		return JSON.stringify({
			found: true,
			x: Math.round(rect.left + rect.width / 2),
			y: Math.round(rect.top + rect.height / 2)
		});
	}
	return JSON.stringify({found: false});
})();
`, selector)

		resultStr, err := m.ExecuteJSWithResult(id, script, timeoutMs)
		if err != nil {
			return nil, fmt.Errorf("failed to find element: %v", err)
		}

		var posResult struct {
			Found bool `json:"found"`
			X     int  `json:"x"`
			Y     int  `json:"y"`
		}
		if err := json.Unmarshal([]byte(resultStr), &posResult); err != nil {
			return nil, fmt.Errorf("failed to parse position: %v", err)
		}

		if !posResult.Found {
			return &result, errors.New("element not found")
		}

		clickX = int32(posResult.X)
		clickY = int32(posResult.Y)
		result.ElementFound = true
	} else {
		// Use provided coordinates
		clickX = x
		clickY = y
		result.ElementFound = true
	}

	log.Printf("[Click] Real CEF click at (%d, %d) for browser %s", clickX, clickY, id)

	// Create mouse event
	me := &cef.TCefMouseEvent{}
	me.X = clickX
	me.Y = clickY

	// Move mouse to position first
	chromium.SendMouseMoveEvent(me, false)

	// Small delay to ensure mouse move is processed
	// In CEF, events are processed synchronously

	// Mouse down (left button, not up, 1 click)
	chromium.SendMouseClickEvent(me, consts.MBT_LEFT, false, 1)

	// Mouse up (left button, up, 1 click)
	chromium.SendMouseClickEvent(me, consts.MBT_LEFT, true, 1)

	result.ClickedX = clickX
	result.ClickedY = clickY

	log.Printf("[Click] CEF click completed at (%d, %d)", clickX, clickY)

	return &result, nil
}
