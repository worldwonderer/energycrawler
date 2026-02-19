package browser

import (
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/energye/energy/v2/cef"
)

// Navigate navigates to a URL and waits for the page to load
// Uses polling of browser.IsLoading() as primary detection mechanism,
// with callback-based detection as a fallback
func (m *Manager) Navigate(id string, url string, timeoutMs int32) (int32, error) {
	window, err := m.GetWindow(id)
	if err != nil {
		return 0, err
	}

	// Create a navigation state for tracking
	navID := fmt.Sprintf("nav-%d", time.Now().UnixNano())
	navState := &NavigationState{
		ID:   navID,
		URL:  url,
		Done: make(chan struct{}),
	}

	// Register the navigation state
	m.RegisterNavigationState(navState)
	defer m.UnregisterNavigationState(navID)

	// Navigate to the URL
	log.Printf("[Navigate] Calling LoadUrl(%s) for browser %s", url, id)
	window.Chromium().LoadUrl(url)
	log.Printf("[Navigate] LoadUrl called, waiting for page load...")

	// Set timeout
	timeout := time.Duration(timeoutMs) * time.Millisecond
	if timeoutMs <= 0 {
		timeout = 30 * time.Second
	}

	// Create a ticker for polling
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	// Create a timeout channel
	timeoutChan := time.After(timeout)

	// Track loading state
	loadStarted := false
	wasLoading := false
	startTime := time.Now()

	// Wait for navigation completion using polling + callback
	for {
		select {
		case <-navState.Done:
			// Callback triggered - navigation completed
			log.Printf("[Navigate] Callback detected navigation completed for %s", url)
			if navState.Error != nil {
				return navState.StatusCode, navState.Error
			}
			return navState.StatusCode, nil

		case <-ticker.C:
			// Polling check
			browser := window.Browser()
			if browser == nil {
				log.Printf("[Navigate] Browser is nil, skipping poll")
				continue
			}

			isLoading := browser.IsLoading()
			elapsed := time.Since(startTime)

			// Log every 5 polls for debugging
			if int(elapsed.Seconds())%5 == 0 && int(elapsed.Seconds()) != int(elapsed.Seconds()-0.1) {
				log.Printf("[Navigate] Polling: isLoading=%v, loadStarted=%v, elapsed=%.1fs", isLoading, loadStarted, elapsed.Seconds())
			}

			// Detect loading start (transition from not loading to loading)
			if isLoading && !wasLoading {
				log.Printf("[Navigate] Page started loading for %s", url)
				loadStarted = true
			}

			// Detect loading complete (transition from loading to not loading)
			if loadStarted && !isLoading && wasLoading {
				log.Printf("[Navigate] Page load complete for %s", url)
				time.Sleep(300 * time.Millisecond)
				m.completeNavigation(navState, 200, nil)
				return 200, nil
			}

			// Fallback: if after 1 second we haven't detected load start,
			// but the page is not loading, assume it's already loaded
			// (handles very fast page loads)
			if !loadStarted && !isLoading && elapsed > time.Second {
				log.Printf("[Navigate] Page appears already loaded (fallback) for %s", url)
				m.completeNavigation(navState, 200, nil)
				return 200, nil
			}

			wasLoading = isLoading

		case <-timeoutChan:
			// Timeout reached
			log.Printf("[Navigate] Navigation timeout for %s after %v (loadStarted: %v)", url, timeout, loadStarted)
			return 0, fmt.Errorf("navigation timeout after %v", timeout)
		}
	}
}

// ExecuteJS executes JavaScript in a browser instance
// Note: This function executes JS but doesn't return the result due to CEF limitations
// For getting JS return values, use ExecuteJSWithResult
func (m *Manager) ExecuteJS(id string, script string) (string, error) {
	window, err := m.GetWindow(id)
	if err != nil {
		return "", err
	}

	// Execute JavaScript - CEF doesn't provide synchronous return values
	window.Chromium().ExecuteJavaScript(script, "", nil, 0)

	// Return empty string - actual result would need IPC implementation
	return "", nil
}

// ExecuteJSWithResult executes JavaScript and returns the result via console message
// This is a workaround for CEF's lack of synchronous JS return values
// The script result is printed to console with a special prefix, captured by SetOnConsoleMessage
func (m *Manager) ExecuteJSWithResult(id string, script string, timeoutMs int32) (string, error) {
	window, err := m.GetWindow(id)
	if err != nil {
		return "", err
	}

	// Generate a unique request ID
	requestID := fmt.Sprintf("js-%d", time.Now().UnixNano())

	// Create channels for result
	resultChan := make(chan string, 1)
	errChan := make(chan error, 1)

	// Store the result channel
	m.storeJSResultChannel(requestID, resultChan, errChan)
	defer m.removeJSResultChannel(requestID)

	// Wrap the script to print result to console with special prefix
	// The console message will be captured by SetOnConsoleMessage in main.go
	wrappedScript := fmt.Sprintf(`
(function() {
	try {
		var result = %s;
		console.log('JSRESULT:%s:' + JSON.stringify(result));
	} catch (e) {
		console.log('JSERROR:%s:' + e.toString());
	}
})();
`, script, requestID, requestID)

	log.Printf("[ExecuteJSWithResult] Executing script with requestID=%s", requestID)

	// Try to get the main frame from Browser, fall back to Chromium if not available
	browser := window.Browser()
	if browser != nil {
		frame := browser.MainFrame()
		if frame != nil {
			window.Chromium().ExecuteJavaScript(wrappedScript, "", frame, 0)
		} else {
			// No main frame, use Chromium directly with nil frame
			window.Chromium().ExecuteJavaScript(wrappedScript, "", nil, 0)
		}
	} else {
		// Browser is nil, use Chromium directly (works for simple scripts)
		log.Printf("[ExecuteJSWithResult] Browser is nil, using Chromium directly")
		window.Chromium().ExecuteJavaScript(wrappedScript, "", nil, 0)
	}

	// Wait for result or timeout
	timeout := time.Duration(timeoutMs) * time.Millisecond
	if timeoutMs <= 0 {
		timeout = 10 * time.Second
	}

	select {
	case result := <-resultChan:
		log.Printf("[ExecuteJSWithResult] Got result for %s: %s", requestID, result)
		return result, nil
	case err := <-errChan:
		log.Printf("[ExecuteJSWithResult] Got error for %s: %v", requestID, err)
		return "", err
	case <-time.After(timeout):
		log.Printf("[ExecuteJSWithResult] Timeout for %s after %v", requestID, timeout)
		return "", fmt.Errorf("JS execution timeout after %v", timeout)
	}
}

// JS result channel storage
var jsResultChannels = struct {
	syncMap map[string]struct {
		result chan string
		err    chan error
	}
	mu sync.RWMutex
}{
	syncMap: make(map[string]struct {
		result chan string
		err    chan error
	}),
}

func (m *Manager) storeJSResultChannel(requestID string, resultChan chan string, errChan chan error) {
	jsResultChannels.mu.Lock()
	defer jsResultChannels.mu.Unlock()
	jsResultChannels.syncMap[requestID] = struct {
		result chan string
		err    chan error
	}{result: resultChan, err: errChan}
}

func (m *Manager) removeJSResultChannel(requestID string) {
	jsResultChannels.mu.Lock()
	defer jsResultChannels.mu.Unlock()
	delete(jsResultChannels.syncMap, requestID)
}

// HandleJSResult handles IPC js-result events
// This should be called from the IPC event handler
func (m *Manager) HandleJSResult(requestID, result, errMsg string) {
	jsResultChannels.mu.RLock()
	channels, exists := jsResultChannels.syncMap[requestID]
	jsResultChannels.mu.RUnlock()

	if !exists {
		return
	}

	if errMsg != "" {
		channels.err <- fmt.Errorf("%s", errMsg)
	} else {
		channels.result <- result
	}
}

// GetMainFrame returns the main frame of the browser
func (m *Manager) GetMainFrame(id string) (*cef.ICefFrame, error) {
	window, err := m.GetWindow(id)
	if err != nil {
		return nil, err
	}

	browser := window.Browser()
	if browser == nil {
		return nil, fmt.Errorf("browser not available: %s", id)
	}

	return browser.MainFrame(), nil
}

// SetupIPCHandlers sets up IPC handlers for JavaScript results
// This should be called in SetBrowserInit
func SetupIPCHandlers(event *cef.BrowserEvent, manager *Manager) {
	// Note: IPC handlers are set up differently in Energy
	// The ipc.On pattern is used for custom events
	// This is a placeholder for when IPC is properly integrated
}
