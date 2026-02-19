package server

import (
	"context"
	"log"
	"sync"

	pb "energy-service/proto"
	"energy-service/browser"
)

// BrowserServer implements the BrowserService gRPC interface
type BrowserServer struct {
	pb.UnimplementedBrowserServiceServer

	manager *browser.Manager
	mu      sync.RWMutex
}

// NewBrowserServer creates a new BrowserServer instance
func NewBrowserServer() *BrowserServer {
	return &BrowserServer{
		manager: browser.NewManager(),
	}
}

// GetManager returns the browser manager
func (s *BrowserServer) GetManager() *browser.Manager {
	return s.manager
}

// Shutdown gracefully shuts down the browser server
func (s *BrowserServer) Shutdown() {
	s.manager.CloseAll()
}

// CreateBrowser creates a new browser instance
func (s *BrowserServer) CreateBrowser(ctx context.Context, req *pb.CreateBrowserRequest) (*pb.CreateBrowserResponse, error) {
	log.Printf("CreateBrowser: %s, headless=%v", req.BrowserId, req.Headless)

	err := s.manager.Create(req.BrowserId, req.Headless)
	if err != nil {
		return &pb.CreateBrowserResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.CreateBrowserResponse{
		Success: true,
	}, nil
}

// CloseBrowser closes a browser instance
func (s *BrowserServer) CloseBrowser(ctx context.Context, req *pb.CloseBrowserRequest) (*pb.CloseBrowserResponse, error) {
	log.Printf("CloseBrowser: %s", req.BrowserId)

	err := s.manager.Close(req.BrowserId)
	if err != nil {
		return &pb.CloseBrowserResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.CloseBrowserResponse{
		Success: true,
	}, nil
}

// Navigate navigates to a URL
func (s *BrowserServer) Navigate(ctx context.Context, req *pb.NavigateRequest) (*pb.NavigateResponse, error) {
	log.Printf("Navigate: %s -> %s", req.BrowserId, req.Url)

	statusCode, err := s.manager.Navigate(req.BrowserId, req.Url, req.TimeoutMs)
	if err != nil {
		return &pb.NavigateResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.NavigateResponse{
		Success:   true,
		StatusCode: statusCode,
	}, nil
}
