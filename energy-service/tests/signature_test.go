package tests

import (
	"testing"

	"energy-service/browser"
)

// TestExecuteSignature_XHS tests XHS signature generation
func TestExecuteSignature_XHS(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		platform  string
		url       string
		wantError bool
	}{
		{
			name:      "XHS signature - non-existent browser",
			browserID: "non-existent",
			platform:  "xhs",
			url:       "https://www.xiaohongshu.com/api/sns/web/v1/search/notes",
			wantError: true,
		},
		{
			name:      "XHS signature - valid browser",
			browserID: "browser1",
			platform:  "xhs",
			url:       "https://www.xiaohongshu.com/search/notes",
			wantError: true, // Will fail because browser doesn't exist
		},
		{
			name:      "XHS signature - empty URL",
			browserID: "browser1",
			platform:  "xhs",
			url:       "",
			wantError: true,
		},
		{
			name:      "XHS signature - complex URL",
			browserID: "browser1",
			platform:  "xhs",
			url:       "https://www.xiaohongshu.com/api/sns/web/v1/search/notes?keyword=test&page=1",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			signatures, err := mgr.ExecuteSignature(tt.browserID, tt.platform, tt.url)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
				if len(signatures) > 0 {
					t.Error("Expected empty signatures for error case")
				}
			} else {
				AssertNoError(t, err)
				if len(signatures) == 0 {
					t.Error("Expected non-empty signatures")
				}
				t.Logf("Signatures: %v", signatures)
			}
		})
	}
}

// TestExecuteSignature_UnsupportedPlatform tests unsupported platform error
func TestExecuteSignature_UnsupportedPlatform(t *testing.T) {
	mgr := browser.NewManager()

	tests := []struct {
		name      string
		browserID string
		platform  string
		url       string
		wantError bool
	}{
		{
			name:      "unsupported platform - random",
			browserID: "browser1",
			platform:  "unsupported",
			url:       "https://example.com",
			wantError: true,
		},
		{
			name:      "unsupported platform - empty",
			browserID: "browser1",
			platform:  "",
			url:       "https://example.com",
			wantError: true,
		},
		{
			name:      "platform case sensitivity - XHS uppercase",
			browserID: "browser1",
			platform:  "XHS",
			url:       "https://example.com",
			wantError: true, // Will fail because browser doesn't exist, but platform is valid
		},
		{
			name:      "platform case sensitivity - Xiaohongshu",
			browserID: "browser1",
			platform:  "xiaohongshu",
			url:       "https://example.com",
			wantError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			signatures, err := mgr.ExecuteSignature(tt.browserID, tt.platform, tt.url)

			if tt.wantError {
				AssertError(t, err)
				t.Logf("Expected error: %v", err)
			} else {
				AssertNoError(t, err)
				t.Logf("Signatures: %v", signatures)
			}
		})
	}
}

// TestGetSignatureHandler tests getting signature handlers for different platforms
func TestGetSignatureHandler(t *testing.T) {
	tests := []struct {
		name          string
		platform      string
		expectHandler bool
		expectedName  string
	}{
		{
			name:          "XHS platform handler",
			platform:      "xhs",
			expectHandler: true,
			expectedName:  "xhs",
		},
		{
			name:          "Xiaohongshu alias",
			platform:      "xiaohongshu",
			expectHandler: true,
			expectedName:  "xhs",
		},
		{
			name:          "Douyin platform handler",
			platform:      "douyin",
			expectHandler: true,
			expectedName:  "douyin",
		},
		{
			name:          "TikTok alias",
			platform:      "tiktok",
			expectHandler: true,
			expectedName:  "douyin",
		},
		{
			name:          "Bilibili platform handler",
			platform:      "bilibili",
			expectHandler: true,
			expectedName:  "bilibili",
		},
		{
			name:          "Kuaishou platform handler",
			platform:      "kuaishou",
			expectHandler: true,
			expectedName:  "kuaishou",
		},
		{
			name:          "Weibo platform handler",
			platform:      "weibo",
			expectHandler: true,
			expectedName:  "weibo",
		},
		{
			name:          "Tieba platform handler",
			platform:      "tieba",
			expectHandler: true,
			expectedName:  "tieba",
		},
		{
			name:          "Zhihu platform handler",
			platform:      "zhihu",
			expectHandler: true,
			expectedName:  "zhihu",
		},
		{
			name:          "Unknown platform",
			platform:      "unknown",
			expectHandler: false,
			expectedName:  "",
		},
		{
			name:          "Empty platform",
			platform:      "",
			expectHandler: false,
			expectedName:  "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			handler := browser.GetSignatureHandler(tt.platform)

			if tt.expectHandler {
				if handler == nil {
					t.Error("Expected handler to be non-nil")
					return
				}
				AssertEqual(t, tt.expectedName, handler.GetPlatformName())
			} else {
				if handler != nil {
					t.Errorf("Expected nil handler, got: %s", handler.GetPlatformName())
				}
			}
		})
	}
}

// TestSignatureResult tests signature result structure
func TestSignatureResult(t *testing.T) {
	t.Run("create signature result", func(t *testing.T) {
		result := &browser.SignatureResult{
			RequestID: "test-request-1",
			Signatures: map[string]string{
				"signature": "abc123",
				"timestamp": "1234567890",
			},
			Error: "",
		}

		AssertEqual(t, "test-request-1", result.RequestID)
		AssertEqual(t, 2, len(result.Signatures))
		AssertEqual(t, "abc123", result.Signatures["signature"])
		AssertEqual(t, "1234567890", result.Signatures["timestamp"])
		AssertEqual(t, "", result.Error)
	})

	t.Run("signature result with error", func(t *testing.T) {
		result := &browser.SignatureResult{
			RequestID:  "test-request-2",
			Signatures: nil,
			Error:      "signature generation failed",
		}

		AssertEqual(t, "test-request-2", result.RequestID)
		if result.Signatures != nil {
			t.Error("Expected nil signatures")
		}
		AssertEqual(t, "signature generation failed", result.Error)
	})
}

// TestSignatureManager tests signature manager operations
func TestSignatureManager(t *testing.T) {
	t.Run("create signature manager", func(t *testing.T) {
		mgr := browser.NewSignatureManager()
		if mgr == nil {
			t.Error("Expected non-nil signature manager")
		}
	})
}

// TestPlatformSignatureHandler tests the platform signature handler interface
func TestPlatformSignatureHandler(t *testing.T) {
	tests := []struct {
		name     string
		platform string
		url      string
	}{
		{
			name:     "XHS handler",
			platform: "xhs",
			url:      "https://www.xiaohongshu.com/api/sns/web/v1/search/notes",
		},
		{
			name:     "Douyin handler",
			platform: "douyin",
			url:      "https://www.douyin.com/api/test",
		},
		{
			name:     "Bilibili handler",
			platform: "bilibili",
			url:      "https://api.bilibili.com/x/web-interface/view",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			handler := browser.GetSignatureHandler(tt.platform)
			if handler == nil {
				t.Fatalf("Expected non-nil handler for platform %s", tt.platform)
			}

			// Test GetPlatformName
			name := handler.GetPlatformName()
			if name == "" {
				t.Error("Expected non-empty platform name")
			}
			t.Logf("Platform name: %s", name)

			// Note: GenerateSignatures requires a real browser window
			// We can't test it without a full Energy runtime
		})
	}
}

// TestSignatureHandlerPlatformNames tests all platform handler names
func TestSignatureHandlerPlatformNames(t *testing.T) {
	platforms := []struct {
		key    string
		name   string
		status string
	}{
		{"xhs", "xhs", "implemented"},
		{"douyin", "douyin", "not_implemented"},
		{"bilibili", "bilibili", "not_implemented"},
		{"kuaishou", "kuaishou", "not_implemented"},
		{"weibo", "weibo", "not_implemented"},
		{"tieba", "tieba", "not_implemented"},
		{"zhihu", "zhihu", "not_implemented"},
	}

	for _, p := range platforms {
		t.Run(p.key, func(t *testing.T) {
			handler := browser.GetSignatureHandler(p.key)
			if handler == nil {
				t.Fatalf("Expected handler for platform %s", p.key)
			}

			AssertEqual(t, p.name, handler.GetPlatformName())
			t.Logf("Platform: %s, Name: %s, Status: %s", p.key, p.name, p.status)
		})
	}
}

// TestAllPlatformSignatures tests that all platform handlers return appropriate results
func TestAllPlatformSignatures(t *testing.T) {
	mgr := browser.NewManager()

	platforms := []string{"xhs", "douyin", "bilibili", "kuaishou", "weibo", "tieba", "zhihu"}

	for _, platform := range platforms {
		t.Run(platform, func(t *testing.T) {
			// All platforms should fail without a browser window
			_, err := mgr.ExecuteSignature("non-existent", platform, "https://example.com")
			AssertError(t, err)
			t.Logf("Platform %s error (expected): %v", platform, err)
		})
	}
}
