package server

import (
	"context"
	"log"

	pb "energy-service/proto"
	"energy-service/browser"
)

// GetCookies retrieves cookies from a browser instance
func (s *BrowserServer) GetCookies(ctx context.Context, req *pb.GetCookiesRequest) (*pb.GetCookiesResponse, error) {
	log.Printf("GetCookies: %s for %s", req.BrowserId, req.Url)

	cookies, err := s.manager.GetCookies(req.BrowserId, req.Url)
	if err != nil {
		return &pb.GetCookiesResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	pbCookies := make([]*pb.Cookie, len(cookies))
	for i, c := range cookies {
		pbCookies[i] = &pb.Cookie{
			Name:     c.Name,
			Value:    c.Value,
			Domain:   c.Domain,
			Path:     c.Path,
			Secure:   c.Secure,
			HttpOnly: c.HttpOnly,
		}
	}

	return &pb.GetCookiesResponse{
		Success: true,
		Cookies: pbCookies,
	}, nil
}

// SetCookies sets cookies in a browser instance
func (s *BrowserServer) SetCookies(ctx context.Context, req *pb.SetCookiesRequest) (*pb.SetCookiesResponse, error) {
	log.Printf("SetCookies: %s (%d cookies)", req.BrowserId, len(req.Cookies))

	cookies := make([]browser.Cookie, len(req.Cookies))
	for i, c := range req.Cookies {
		cookies[i] = browser.Cookie{
			Name:     c.Name,
			Value:    c.Value,
			Domain:   c.Domain,
			Path:     c.Path,
			Secure:   c.Secure,
			HttpOnly: c.HttpOnly,
		}
	}

	err := s.manager.SetCookies(req.BrowserId, cookies)
	if err != nil {
		return &pb.SetCookiesResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.SetCookiesResponse{
		Success: true,
	}, nil
}

// ExecuteJS executes JavaScript in a browser instance
// Uses IPC to get the result back from JavaScript
func (s *BrowserServer) ExecuteJS(ctx context.Context, req *pb.ExecuteJSRequest) (*pb.ExecuteJSResponse, error) {
	log.Printf("ExecuteJS: %s (script length: %d)", req.BrowserId, len(req.Script))

	// Use ExecuteJSWithResult to get the actual result via IPC
	result, err := s.manager.ExecuteJSWithResult(req.BrowserId, req.Script, 10000) // 10 second timeout
	if err != nil {
		return &pb.ExecuteJSResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.ExecuteJSResponse{
		Success: true,
		Result:  result,
	}, nil
}

// SetProxy configures proxy for a browser instance
func (s *BrowserServer) SetProxy(ctx context.Context, req *pb.SetProxyRequest) (*pb.SetProxyResponse, error) {
	log.Printf("SetProxy: %s -> %s", req.BrowserId, req.ProxyUrl)

	err := s.manager.SetProxy(req.BrowserId, req.ProxyUrl, req.Username, req.Password)
	if err != nil {
		return &pb.SetProxyResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.SetProxyResponse{
		Success: true,
	}, nil
}

// ExecuteSignature executes platform-specific signature generation
func (s *BrowserServer) ExecuteSignature(ctx context.Context, req *pb.ExecuteSignatureRequest) (*pb.ExecuteSignatureResponse, error) {
	log.Printf("ExecuteSignature: %s for %s at %s", req.BrowserId, req.Platform, req.Url)

	signatures, err := s.manager.ExecuteSignature(req.BrowserId, req.Platform, req.Url)
	if err != nil {
		return &pb.ExecuteSignatureResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.ExecuteSignatureResponse{
		Success:    true,
		Signatures: signatures,
	}, nil
}

// Click clicks on an element specified by CSS selector or coordinates
func (s *BrowserServer) Click(ctx context.Context, req *pb.ClickRequest) (*pb.ClickResponse, error) {
	log.Printf("Click: %s (selector=%s, x=%d, y=%d)", req.BrowserId, req.Selector, req.X, req.Y)

	result, err := s.manager.Click(req.BrowserId, req.Selector, req.X, req.Y, req.TimeoutMs)
	if err != nil {
		return &pb.ClickResponse{
			Success: false,
			Error:   err.Error(),
		}, nil
	}

	return &pb.ClickResponse{
		Success:      true,
		ElementFound: result.ElementFound,
		ClickedX:     result.ClickedX,
		ClickedY:     result.ClickedY,
	}, nil
}
