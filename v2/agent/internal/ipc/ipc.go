// Package ipc is the control channel between the desktop app (or CLI) and the
// agent. It is a Windows named pipe, not a network port, so a web page in the
// seller's browser has no way to reach it. Access is limited by the pipe's ACL.
//
// Wire format: one JSON request per connection, one JSON response back.
package ipc

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"time"
)

// PipeName is where the agent listens.
const PipeName = `\\.\pipe\productify-node`

// SDDL for the pipe: SYSTEM and Administrators full control; interactive
// (signed-in, on-console) users read/write. Network logons, services and
// other non-interactive accounts get nothing.
const SDDL = "D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;IU)"

const maxRequest = 64 << 10

// Request ops: status, pair, live, limits, emergency_stop, logs.
type Request struct {
	Op       string   `json:"op"`
	RentalID string   `json:"rental_id,omitempty"`
	Token    string   `json:"token,omitempty"`
	Code     string   `json:"code,omitempty"` // "<listing id>.<token>", replaces RentalID+Token
	Live     *bool    `json:"live,omitempty"`
	MemoryMB *int     `json:"memory_mb,omitempty"`
	CPUs     *float64 `json:"cpus,omitempty"`
	DiskGB   *int     `json:"disk_gb,omitempty"`
	ShareGPU *bool    `json:"share_gpu,omitempty"`
	MaxTempC *int     `json:"max_gpu_temp_c,omitempty"`
}

type Response struct {
	OK    bool            `json:"ok"`
	Error string          `json:"error,omitempty"`
	Data  json.RawMessage `json:"data,omitempty"`
}

// Handler answers one request.
type Handler func(Request) (any, error)

// Serve accepts connections on l until ctx ends.
func Serve(ctx context.Context, l net.Listener, h Handler) error {
	go func() { <-ctx.Done(); l.Close() }()
	for {
		c, err := l.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		go handle(c, h)
	}
}

func handle(c net.Conn, h Handler) {
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(30 * time.Second))
	var req Request
	resp := Response{}
	if err := json.NewDecoder(io.LimitReader(c, maxRequest)).Decode(&req); err != nil {
		resp.Error = "bad request"
	} else if data, err := h(req); err != nil {
		resp.Error = err.Error()
	} else {
		resp.OK = true
		resp.Data, _ = json.Marshal(data)
	}
	_ = json.NewEncoder(c).Encode(resp)
}

// Call sends one request over an already-dialled connection.
func Call(c net.Conn, req Request) (json.RawMessage, error) {
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(60 * time.Second))
	if err := json.NewEncoder(c).Encode(req); err != nil {
		return nil, err
	}
	var resp Response
	if err := json.NewDecoder(io.LimitReader(c, 4<<20)).Decode(&resp); err != nil {
		return nil, err
	}
	if !resp.OK {
		return nil, errors.New(resp.Error)
	}
	return resp.Data, nil
}
