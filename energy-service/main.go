package main

import (
	"log"
	"net"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"

	"google.golang.org/grpc"

	pb "energy-service/proto"
	"energy-service/server"

	"github.com/energye/energy/v2/cef"
	"github.com/energye/energy/v2/cef/process"
	"github.com/energye/energy/v2/consts"
	"github.com/energye/golcl/lcl"
)

const (
	defaultPort            = ":50051"
	defaultRemoteDebugPort = 0
)

func main() {
	// Global initialization - required for every Energy application
	cef.GlobalInit(nil, nil)

	// Create application
	app := cef.NewApplication()
	app.SetUseMockKeyChain(true)
	app.SetEnableGPU(false) // Disable GPU for headless/service use
	app.SetNoSandbox(true)  // Disable sandbox for service context
	remoteDebugPort := getEnvIntOrDefault("ENERGY_DEBUG_PORT", defaultRemoteDebugPort)
	app.SetRemoteDebuggingPort(int32(remoteDebugPort))

	// CRITICAL: Workaround for Fontations font rendering crash
	// The Fontations backend (new in Chrome 136+) has a bug that causes SIGILL crashes
	// when rendering certain fonts on some websites (e.g., Xiaohongshu)
	// See: https://bugs.chromium.org/p/chromium/issues/detail?id=349952802
	// Try to disable fontations via features flag
	app.SetDisableFeatures("FontationsBackend")

	// Only run gRPC server in the main process
	// CEF creates multiple subprocesses (renderer, GPU, etc.) that also run main()
	if !process.Args.IsMain() {
		// This is a subprocess (renderer, GPU, etc.), just run CEF and return
		cef.Run(app)
		return
	}

	log.Println("[Main] Energy Browser Service starting...")
	log.Printf("[Main] ChromeVersion: %s", app.ChromeVersion())
	log.Printf("[Main] RemoteDebuggingPort: %d", remoteDebugPort)

	// Get the browser manager from the server
	browserServer := server.NewBrowserServer()
	manager := browserServer.GetManager()

	// Configure browser window defaults
	cef.BrowserWindow.Config.Url = "https://example.com"
	cef.BrowserWindow.Config.Title = "Energy Browser Service"

	// Set up browser initialization callback
	// This is called when the browser window is created
	cef.BrowserWindow.SetBrowserInit(func(event *cef.BrowserEvent, window cef.IBrowserWindow) {
		log.Println("[Main] Browser window initialized")

		// Store the default window in the manager
		manager.SetDefaultWindow(window)

		// Use window.Chromium().SetOn* for callbacks (more stable on macOS)
		window.Chromium().SetOnLoadStart(func(sender lcl.IObject, browser *cef.ICefBrowser, frame *cef.ICefFrame, transitionType consts.TCefTransitionType) {
			log.Printf("[OnLoadStart] URL: %s, isMain: %v", frame.Url(), frame.IsMain())
		})

		window.Chromium().SetOnLoadEnd(func(sender lcl.IObject, browser *cef.ICefBrowser, frame *cef.ICefFrame, httpStatusCode int32) {
			log.Printf("[OnLoadEnd] URL: %s, Status: %d", frame.Url(), httpStatusCode)
		})

		window.Chromium().SetOnLoadingStateChange(func(sender lcl.IObject, browser *cef.ICefBrowser, isLoading, canGoBack, canGoForward bool) {
			log.Printf("[OnLoadingStateChange] isLoading: %v", isLoading)
		})

		window.Chromium().SetOnLoadError(func(sender lcl.IObject, browser *cef.ICefBrowser, frame *cef.ICefFrame, errorCode consts.CEF_NET_ERROR, errorText, failedUrl string) {
			log.Printf("[OnLoadError] URL: %s, Error: %s", failedUrl, errorText)
		})

		// Set up cookie callbacks for GetCookies gRPC method
		log.Println("[Main] Setting up cookie callbacks...")
		manager.SetupCookieCallbacks(event)

		// Capture console messages to get JavaScript results
		// JavaScript uses console.log('JSRESULT:requestID:result') to send results back
		chromium := window.Chromium()
		log.Printf("[Main] Setting up OnConsoleMessage callback, chromium valid: %v", chromium.IsValid())
		chromium.SetOnConsoleMessage(func(sender lcl.IObject, browser *cef.ICefBrowser, level consts.TCefLogSeverity, message, source string, line int32) bool {
			// Check for JS result message
			if len(message) > 8 && message[:8] == "JSRESULT" {
				// Format: JSRESULT:requestID:result
				parts := splitN(message, ":", 3)
				if len(parts) == 3 {
					requestID := parts[1]
					result := parts[2]
					log.Printf("[Console] JS result for %s: %s", requestID, result)
					manager.HandleJSResult(requestID, result, "")
				}
				return true // suppress the message
			}
			// Check for JS error message
			if len(message) > 7 && message[:7] == "JSERROR" {
				parts := splitN(message, ":", 3)
				if len(parts) == 3 {
					requestID := parts[1]
					errMsg := parts[2]
					log.Printf("[Console] JS error for %s: %s", requestID, errMsg)
					manager.HandleJSResult(requestID, "", errMsg)
				}
				return true
			}
			// Log other console messages for debugging
			log.Printf("[Console] %s", message)
			return false // allow the message to be displayed
		})

		log.Println("[Main] Callbacks registered")
	})

	var grpcServer *grpc.Server
	grpcReady := make(chan struct{})
	grpcErr := make(chan error, 1)

	// Start gRPC server in a goroutine
	go func() {
		port := getEnvOrDefault("GRPC_PORT", defaultPort)

		lis, err := net.Listen("tcp", port)
		if err != nil {
			log.Printf("[gRPC] Failed to listen on %s: %v", port, err)
			grpcErr <- err
			return
		}

		grpcServer = grpc.NewServer()
		pb.RegisterBrowserServiceServer(grpcServer, browserServer)

		log.Printf("[gRPC] Energy Browser gRPC Server listening on %s", port)
		close(grpcReady)

		if err := grpcServer.Serve(lis); err != nil {
			log.Printf("[gRPC] Server error: %v", err)
		}
	}()

	// Handle OS signals in a goroutine
	// NOTE: Due to Energy framework bug (github.com/energye/energy/issues/53),
	// calling lcl.Application.Terminate() or window.Close() on macOS causes
	// NSInvalidArgumentException: -[TAppDelegate tryToTerminateApplication:]:
	// unrecognized selector. For service mode, we only stop gRPC and let the
	// browser process continue running.
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

		select {
		case sig := <-sigChan:
			log.Printf("[Signal] Received %v, initiating shutdown...", sig)
		case err := <-grpcErr:
			log.Printf("[gRPC] Startup failed: %v, keeping browser running...", err)
			// Don't shutdown on gRPC error - just keep the browser running
			return
		}

		// Stop gRPC server
		if grpcServer != nil {
			log.Println("[Shutdown] Stopping gRPC server...")
			grpcServer.GracefulStop()
		}
		browserServer.Shutdown()
		log.Println("[Shutdown] gRPC server shutdown complete")

		// On macOS, due to the framework bug, we cannot cleanly terminate the
		// application from signal handler. The service will exit when the
		// main process ends. For production use, consider using a process
		// manager (like systemd or launchd) to manage the service lifecycle.
		// For now, we exit with os.Exit(0) which is cleaner than a crash.
		log.Println("[Shutdown] Exiting...")
		os.Exit(0)
	}()

	// Run Energy application on the main thread (this blocks)
	cef.Run(app)
	log.Println("[Main] Energy application exited")
}

func getEnvOrDefault(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func getEnvIntOrDefault(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if parsed, err := strconv.Atoi(val); err == nil {
			return parsed
		}
		log.Printf("[Config] Invalid %s=%q, fallback to %d", key, val, defaultVal)
	}
	return defaultVal
}

// splitN splits a string into at most n parts
func splitN(s string, sep string, n int) []string {
	return strings.SplitN(s, sep, n)
}
