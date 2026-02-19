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
	case "douyin", "tiktok":
		return &DouyinSignatureHandler{}
	case "bilibili":
		return &BilibiliSignatureHandler{}
	case "kuaishou":
		return &KuaishouSignatureHandler{}
	case "weibo":
		return &WeiboSignatureHandler{}
	case "tieba":
		return &TiebaSignatureHandler{}
	case "zhihu":
		return &ZhihuSignatureHandler{}
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

// DouyinSignatureHandler handles Douyin signature generation
type DouyinSignatureHandler struct{}

func (h *DouyinSignatureHandler) GetPlatformName() string {
	return "douyin"
}

func (h *DouyinSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// TODO: Implement Douyin signature generation
	return map[string]string{
		"platform": "douyin",
		"status":   "not_implemented",
	}, nil
}

// BilibiliSignatureHandler handles Bilibili signature generation
type BilibiliSignatureHandler struct{}

func (h *BilibiliSignatureHandler) GetPlatformName() string {
	return "bilibili"
}

func (h *BilibiliSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// TODO: Implement Bilibili signature generation
	return map[string]string{
		"platform": "bilibili",
		"status":   "not_implemented",
	}, nil
}

// KuaishouSignatureHandler handles Kuaishou signature generation
type KuaishouSignatureHandler struct{}

func (h *KuaishouSignatureHandler) GetPlatformName() string {
	return "kuaishou"
}

func (h *KuaishouSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// TODO: Implement Kuaishou signature generation
	return map[string]string{
		"platform": "kuaishou",
		"status":   "not_implemented",
	}, nil
}

// WeiboSignatureHandler handles Weibo signature generation
type WeiboSignatureHandler struct{}

func (h *WeiboSignatureHandler) GetPlatformName() string {
	return "weibo"
}

func (h *WeiboSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// TODO: Implement Weibo signature generation
	return map[string]string{
		"platform": "weibo",
		"status":   "not_implemented",
	}, nil
}

// TiebaSignatureHandler handles Tieba signature generation
type TiebaSignatureHandler struct{}

func (h *TiebaSignatureHandler) GetPlatformName() string {
	return "tieba"
}

func (h *TiebaSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// TODO: Implement Tieba signature generation
	return map[string]string{
		"platform": "tieba",
		"status":   "not_implemented",
	}, nil
}

// ZhihuSignatureHandler handles Zhihu signature generation
type ZhihuSignatureHandler struct{}

func (h *ZhihuSignatureHandler) GetPlatformName() string {
	return "zhihu"
}

func (h *ZhihuSignatureHandler) GenerateSignatures(url string, browserWindow cef.IBrowserWindow) (map[string]string, error) {
	// TODO: Implement Zhihu signature generation
	return map[string]string{
		"platform": "zhihu",
		"status":   "not_implemented",
	}, nil
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
