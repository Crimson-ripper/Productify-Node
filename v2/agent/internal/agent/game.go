package agent

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"productifynode/internal/ids"
)

// GameVMs runs Gamezone sessions: one Hyper-V VM with a GPU partition per session, made and
// destroyed by gamezone-vm.ps1. Only one session (game or container job) runs per machine.
type GameVMs struct {
	// Run executes the VM script with the given arguments and returns its stdout.
	Run func(ctx context.Context, args ...string) ([]byte, error)

	mu        sync.Mutex
	active    string // job id of the running session, "" when idle
	startedAt time.Time
}

var (
	errGameBusy  = errors.New("this machine already has a renter")
	errNoBaseVHD = errors.New("this machine has no Gamezone base image set up yet")
)

// Active is the running session's job id, or "".
func (g *GameVMs) Active() string {
	if g == nil {
		return ""
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.active
}

// Start creates and boots the session VM; it returns what the script reported (VM name etc.).
func (g *GameVMs) Start(ctx context.Context, jobID, baseVHD string) (map[string]any, error) {
	if err := ids.ValidJobID(jobID); err != nil {
		return nil, err
	}
	if baseVHD == "" {
		return nil, errNoBaseVHD
	}
	g.mu.Lock()
	if g.active != "" {
		g.mu.Unlock()
		return nil, errGameBusy
	}
	g.active, g.startedAt = jobID, time.Now() // reserve before the slow part
	g.mu.Unlock()

	out, err := g.Run(ctx, "-Action", "Start", "-BaseVhd", baseVHD, "-Session", jobID)
	if err != nil {
		_, _ = g.Run(context.Background(), "-Action", "Stop", "-Session", jobID) // clean up a half-made VM
		g.mu.Lock()
		g.active = ""
		g.mu.Unlock()
		return nil, fmt.Errorf("couldn't start the Gamezone VM: %w", err)
	}
	info := map[string]any{}
	_ = json.Unmarshal([]byte(lastLine(out)), &info)
	return info, nil
}

// Stop destroys the session VM and its disk. Stopping an unknown or finished session is fine.
func (g *GameVMs) Stop(ctx context.Context, jobID string) error {
	if err := ids.ValidJobID(jobID); err != nil {
		return err
	}
	if _, err := g.Run(ctx, "-Action", "Stop", "-Session", jobID); err != nil {
		return fmt.Errorf("couldn't remove the Gamezone VM: %w", err)
	}
	g.mu.Lock()
	if g.active == jobID {
		g.active = ""
	}
	g.mu.Unlock()
	return nil
}

func lastLine(b []byte) string {
	lines := strings.Split(strings.TrimSpace(string(b)), "\n")
	return strings.TrimSpace(lines[len(lines)-1])
}

// startGame checks everything the backend can't see before a VM is made.
func (a *Agent) startGame(ctx context.Context, jobID string) map[string]any {
	if a.Games == nil || a.Games.Run == nil {
		return fail("unsupported")
	}
	st := a.Status()
	switch {
	case !st.Live:
		return fail("this machine is paused by its owner")
	case !st.Gamezone.Eligible:
		return fail("this machine can't host Gamezone: " + strings.Join(st.Gamezone.Reasons, " "))
	case a.Runner.Count() > 0:
		return fail(errGameBusy.Error())
	}
	info, err := a.Games.Start(ctx, jobID, a.Store.Get().GamezoneBaseVHD)
	if err != nil {
		return fail(err.Error())
	}
	a.Log.Info("game session started", "job", jobID)
	return map[string]any{"ok": true, "vm": info}
}

// NewGameVMs runs the VM script with Windows PowerShell; nil off Windows or when the script is missing.
func NewGameVMs(script string) *GameVMs {
	return newGameVMs(script)
}
