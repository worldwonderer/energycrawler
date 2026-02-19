package browser

import (
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"sync"
	"time"

	"github.com/energye/energy/v2/cef"
)

// PlatformSignatureHandler defines the interface for platform-specific signature handlers
type PlatformSignatureHandler interface {
	GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error)
	GetPlatformName() string
}

// SignatureManager manages signature generation across platforms
type SignatureManager struct {
	mu         sync.Mutex
	pending    map[string]chan *SignatureResult
	resultChan chan *SignatureResult
}

// SignatureResult holds the result of a signature request
type SignatureResult struct {
	RequestID  string
	Signatures map[string]string
	Error      string
}

// NewSignatureManager creates a new SignatureManager
func NewSignatureManager() *SignatureManager {
	return &SignatureManager{
		pending:    make(map[string]chan *SignatureResult),
		resultChan: make(chan *SignatureResult, 100),
	}
}

// ExecuteSignature executes platform-specific signature generation
// Based on patterns validated in energy-spike
func (m *Manager) ExecuteSignature(id string, platform string, url string) (map[string]string, error) {
	window, err := m.GetWindow(id)
	if err != nil {
		return nil, err
	}

	// Get the appropriate signature handler for the platform
	handler := GetSignatureHandler(platform)
	if handler == nil {
		return nil, fmt.Errorf("unsupported platform: %s", platform)
	}

	// Generate signatures using the platform-specific handler
	return handler.GenerateSignatures(url, window)
}

// GetSignatureHandler returns the signature handler for a platform
func GetSignatureHandler(platform string) PlatformSignatureHandler {
	switch platform {
	case "xhs", "xiaohongshu":
		return &XHSSignatureHandler{}
	default:
		return nil
	}
}

// XHSSignatureHandler handles XHS (Xiaohongshu) signature generation
type XHSSignatureHandler struct{}

func (h *XHSSignatureHandler) GetPlatformName() string {
	return "xhs"
}

func (h *XHSSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// Based on energy-spike implementation
	// XHS uses window.mnsv2(signStr, md5Str) for signature generation

	// Calculate the sign string and MD5
	// For XHS, signStr = uri + jsonData
	uri := extractURI(url)
	signStr := uri + "{}" // Empty data for basic signature
	hash := md5.Sum([]byte(signStr))
	md5Str := hex.EncodeToString(hash[:])

	// Get the main frame for JS execution
	browser := browserWindow.Browser()
	if browser == nil {
		return nil, fmt.Errorf("browser not available")
	}
	frame := browser.MainFrame()
	if frame == nil {
		return nil, fmt.Errorf("main frame not available")
	}

	requestID := fmt.Sprintf("sig-%d", time.Now().UnixNano())

	resultChan := make(chan string, 1)
	errChan := make(chan error, 1)

	// Register with the global jsResultChannels (same one used by ExecuteJSWithResult)
	jsResultChannels.mu.Lock()
	jsResultChannels.syncMap[requestID] = struct {
		result chan string
		err    chan error
	}{result: resultChan, err: errChan}
	jsResultChannels.mu.Unlock()

	// Build the wrapped script
	wrappedScript := fmt.Sprintf(`
(function() {
	try {
		var result = window.mnsv2('%s', '%s');
		console.log('JSRESULT:%s:' + JSON.stringify(result));
	} catch (e) {
		console.log('JSERROR:%s:' + e.toString());
	}
})();
`, escapeJSString(signStr), escapeJSString(md5Str), requestID, requestID)

	// Execute the JS with the correct frame parameter (same as ExecuteJSWithResult)
	browserWindow.Chromium().ExecuteJavaScript(wrappedScript, "", frame, 0)

	// Cleanup on return
	defer func() {
		jsResultChannels.mu.Lock()
		delete(jsResultChannels.syncMap, requestID)
		jsResultChannels.mu.Unlock()
	}()

	// Wait for result with timeout
	select {
	case result := <-resultChan:
		return map[string]string{"signature": result}, nil
	case err := <-errChan:
		return nil, fmt.Errorf("signature error: %v", err)
	case <-time.After(15 * time.Second):
		return nil, fmt.Errorf("signature generation timeout")
	}
}

// Helper functions

func escapeJSString(s string) string {
	result := ""
	for _, c := range s {
		switch c {
		case '\\':
			result += "\\\\"
		case '\'':
			result += "\\'"
		case '\n':
			result += "\\n"
		case '\r':
			result += "\\r"
		default:
			result += string(c)
		}
	}
	return result
}

func extractURI(url string) string {
	// Extract URI path from full URL
	// For XHS, this would be like "/api/sns/web/v1/search/notes"
	// Simple implementation - in production, use proper URL parsing
	return "/"
}
