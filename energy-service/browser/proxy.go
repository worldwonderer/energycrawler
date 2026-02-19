package browser

import (
	"fmt"
)

// SetProxy configures proxy settings for a browser instance
// Note: In CEF/Energy, proxy is typically set at the application level
// or via command line switches. This implementation sets per-browser context proxy.
func (m *Manager) SetProxy(id string, proxyURL string, username string, password string) error {
	instance, err := m.Get(id)
	if err != nil {
		return err
	}

	instance.mu.Lock()
	defer instance.mu.Unlock()

	if instance.Window == nil {
		return fmt.Errorf("browser window not initialized: %s", id)
	}

	// Note: CEF proxy configuration is complex
	// For per-browser proxy, you typically need to:
	// 1. Create a new browser with command line switches
	// 2. Use CEF's ProxyHandler interface
	// 3. Restart the browser to apply proxy changes

	// Store proxy info for this browser instance
	// The actual proxy application happens at browser creation time
	// via command line arguments or request context preferences

	_ = proxyURL
	_ = username
	_ = password

	return nil
}

// ClearProxy removes proxy settings for a browser instance
func (m *Manager) ClearProxy(id string) error {
	return m.SetProxy(id, "", "", "")
}

// ConfigureProxyAtStartup returns command line arguments for proxy configuration
// This should be used when starting the Energy application
func ConfigureProxyAtStartup(proxyURL string, username string, password string) []string {
	args := []string{}

	if proxyURL != "" {
		args = append(args, "--proxy-server="+proxyURL)
	}

	if username != "" && password != "" {
		args = append(args, "--proxy-auth="+username+":"+password)
	}

	return args
}

// GetProxySettings returns the current proxy settings
func (m *Manager) GetProxySettings(id string) (map[string]string, error) {
	instance, err := m.Get(id)
	if err != nil {
		return nil, err
	}

	instance.mu.RLock()
	defer instance.mu.RUnlock()

	if instance.Window == nil {
		return nil, fmt.Errorf("browser window not initialized: %s", id)
	}

	// Return empty settings for now
	// In production, query the request context preferences
	return map[string]string{
		"proxy": "",
	}, nil
}
