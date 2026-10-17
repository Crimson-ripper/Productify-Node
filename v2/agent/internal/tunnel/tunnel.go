// Package tunnel keeps one outbound WebSocket to the backend and dispatches
// the backend's requests to a Handler. The agent never listens on a port.
package tunnel

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math/rand/v2"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/coder/websocket"
)

const (
	Path              = "/ws/node/v1"
	heartbeatInterval = 15 * time.Second
	// CloseUnauthorized is sent by the backend when the pairing is rejected.
	CloseUnauthorized websocket.StatusCode = 4401
)

// ErrUnauthorized means the backend rejected the pairing token; retrying won't help.
var ErrUnauthorized = errors.New("the backend rejected this pairing token")

// Request is a frame from the backend.
type Request struct {
	Type     string   `json:"type"`
	ID       string   `json:"id"`
	JobID    string   `json:"job_id,omitempty"`
	Template string   `json:"template,omitempty"`
	Argv     []string `json:"argv,omitempty"`
	Python   string   `json:"python,omitempty"`
	TimeoutS int      `json:"timeout_s,omitempty"`
}

// Handler answers backend requests and supplies hello/heartbeat contents.
type Handler interface {
	Hello() map[string]any
	Heartbeat() map[string]any
	Handle(ctx context.Context, req Request) map[string]any
}

// Client is one paired node's connection.
type Client struct {
	BackendURL string
	RentalID   string
	Token      string
	Handler    Handler
	Log        *slog.Logger

	mu        sync.Mutex
	conn      *websocket.Conn
	connected bool
}

func (c *Client) Connected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected
}

// Send writes an unsolicited frame (an event) if connected.
func (c *Client) Send(ctx context.Context, msg map[string]any) error {
	c.mu.Lock()
	conn := c.conn
	c.mu.Unlock()
	if conn == nil {
		return errors.New("not connected")
	}
	return writeJSON(ctx, conn, msg)
}

// Run connects and reconnects until ctx is cancelled or the token is rejected.
func (c *Client) Run(ctx context.Context) error {
	backoff := time.Second
	for {
		started := time.Now()
		err := c.session(ctx)
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if errors.Is(err, ErrUnauthorized) {
			c.Log.Error("pairing rejected; stopping until re-paired")
			return err
		}
		if time.Since(started) > time.Minute {
			backoff = time.Second // it was a healthy session; reconnect quickly
		}
		wait := backoff + time.Duration(rand.Int64N(int64(backoff/2)+1))
		c.Log.Warn("tunnel disconnected", "err", err, "retry_in", wait.Round(time.Second))
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(wait):
		}
		if backoff < time.Minute {
			backoff *= 2
		}
	}
}

func wsURL(base string) string {
	base = strings.TrimRight(base, "/")
	switch {
	case strings.HasPrefix(base, "https://"):
		return "wss://" + strings.TrimPrefix(base, "https://") + Path
	case strings.HasPrefix(base, "http://"):
		return "ws://" + strings.TrimPrefix(base, "http://") + Path
	}
	return base + Path
}

func (c *Client) session(ctx context.Context) error {
	dialCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	hdr := http.Header{}
	hdr.Set("Authorization", "Bearer "+c.Token)
	hdr.Set("X-Rental-Id", c.RentalID)
	conn, resp, err := websocket.Dial(dialCtx, wsURL(c.BackendURL), &websocket.DialOptions{HTTPHeader: hdr})
	if err != nil {
		if resp != nil && (resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden) {
			return ErrUnauthorized
		}
		return err
	}
	conn.SetReadLimit(1 << 20)
	defer conn.CloseNow()

	c.mu.Lock()
	c.conn, c.connected = conn, true
	c.mu.Unlock()
	defer func() {
		c.mu.Lock()
		c.conn, c.connected = nil, false
		c.mu.Unlock()
	}()

	if err := writeJSON(ctx, conn, with(c.Handler.Hello(), "type", "hello")); err != nil {
		return err
	}
	c.Log.Info("tunnel connected", "rental", c.RentalID)

	sessCtx, stop := context.WithCancel(ctx)
	defer stop()
	go func() {
		t := time.NewTicker(heartbeatInterval)
		defer t.Stop()
		for {
			select {
			case <-sessCtx.Done():
				return
			case <-t.C:
				if err := writeJSON(sessCtx, conn, with(c.Handler.Heartbeat(), "type", "heartbeat")); err != nil {
					stop()
					return
				}
			}
		}
	}()

	for {
		_, data, err := conn.Read(sessCtx)
		if err != nil {
			if websocket.CloseStatus(err) == CloseUnauthorized {
				return ErrUnauthorized
			}
			return err
		}
		var req Request
		if err := json.Unmarshal(data, &req); err != nil || req.ID == "" {
			c.Log.Warn("ignoring malformed frame")
			continue
		}
		go func(req Request) {
			reply := c.Handler.Handle(sessCtx, req)
			reply["type"], reply["re"] = "result", req.ID
			if err := writeJSON(sessCtx, conn, reply); err != nil {
				c.Log.Warn("reply failed", "err", err)
			}
		}(req)
	}
}

var writeMu sync.Mutex // one writer at a time per process; there is only one connection

func writeJSON(ctx context.Context, conn *websocket.Conn, v any) error {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Errorf("encode: %w", err)
	}
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	writeMu.Lock()
	defer writeMu.Unlock()
	return conn.Write(ctx, websocket.MessageText, b)
}

func with(m map[string]any, k string, v any) map[string]any {
	if m == nil {
		m = map[string]any{}
	}
	m[k] = v
	return m
}
