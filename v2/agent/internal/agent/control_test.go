package agent

import (
	"strings"
	"testing"

	"productifynode/internal/config"
	"productifynode/internal/ipc"
)

func TestControlPairingStartsPausedAndHidesToken(t *testing.T) {
	a := newAgent(t, "https://example.invalid", true)
	_, _ = a.Store.Update(func(s *config.Settings) { s.RentalID, s.Token, s.Live = "", "", false })

	on := true
	if _, err := a.Control(ipc.Request{Op: "live", Live: &on}); err == nil {
		t.Error("went live without a pairing")
	}
	if _, err := a.Control(ipc.Request{Op: "pair", RentalID: "r-abc123def4", Token: "nope"}); err == nil {
		t.Error("bad token accepted")
	}
	if _, err := a.Control(ipc.Request{Op: "pair", RentalID: "r-abc123def4", Token: "ptok_0123456789abcdef"}); err != nil {
		t.Fatal(err)
	}
	if a.Store.Get().Live {
		t.Error("a new pairing must start paused")
	}
	out, _ := a.Control(ipc.Request{Op: "status"})
	m := out.(map[string]any)
	s := m["settings"].(config.Settings)
	if strings.Contains(s.Token, "0123456789") {
		t.Errorf("status leaked the token: %q", s.Token)
	}
	if _, err := a.Control(ipc.Request{Op: "live", Live: &on}); err != nil || !a.Store.Get().Live {
		t.Errorf("couldn't go live after pairing: %v", err)
	}
}

func TestControlPairingCode(t *testing.T) {
	a := newAgent(t, "https://example.invalid", false)
	if _, err := a.Control(ipc.Request{Op: "pair", Code: "r-abc123def4ptok_0123456789abcdef"}); err == nil {
		t.Error("code without the separator accepted")
	}
	if _, err := a.Control(ipc.Request{Op: "pair", Code: "r-abc123def4.ptok_bad"}); err == nil {
		t.Error("bad token inside code accepted")
	}
	if _, err := a.Control(ipc.Request{Op: "pair", Code: "  r-1a2b3c4d5e.ptok_fedcba9876543210 "}); err != nil {
		t.Fatal(err)
	}
	s := a.Store.Get()
	if s.RentalID != "r-1a2b3c4d5e" || s.Token != "ptok_fedcba9876543210" || s.Live {
		t.Errorf("pairing code not applied: %+v", s)
	}
}

func TestHelloReportsHardware(t *testing.T) {
	a := newAgent(t, "https://example.invalid", false)
	h := a.Hello()
	if h["cpu_cores"].(int) < 1 {
		t.Error("cpu_cores missing")
	}
	if _, ok := h["ram_mb"]; !ok {
		t.Error("ram_mb missing from hello")
	}
}

func TestControlLimitsValidated(t *testing.T) {
	a := newAgent(t, "https://example.invalid", true)
	tooHot, tooSmall := 120, 64
	if _, err := a.Control(ipc.Request{Op: "limits", MaxTempC: &tooHot}); err == nil {
		t.Error("unsafe temperature accepted")
	}
	if _, err := a.Control(ipc.Request{Op: "limits", MemoryMB: &tooSmall}); err == nil {
		t.Error("tiny memory limit accepted")
	}
	ok := 8192
	if _, err := a.Control(ipc.Request{Op: "limits", MemoryMB: &ok}); err != nil || a.Store.Get().MemoryMB != 8192 {
		t.Errorf("valid limit rejected: %v", err)
	}
}

func TestEmergencyStopPauses(t *testing.T) {
	a := newAgent(t, "https://example.invalid", true)
	a.mu.Lock()
	a.dockerReady = true
	a.mu.Unlock()
	_ = a.Runner.Start(t.Context(), "inst-1", "python")
	out, err := a.Control(ipc.Request{Op: "emergency_stop"})
	if err != nil || out.(map[string]int)["jobs_stopped"] != 1 || a.Store.Get().Live {
		t.Errorf("emergency stop: %v %v live=%v", out, err, a.Store.Get().Live)
	}
}
