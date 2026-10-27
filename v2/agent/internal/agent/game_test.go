package agent

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"

	"productifynode/internal/config"
	"productifynode/internal/tunnel"
)

type fakeVMScript struct {
	mu    sync.Mutex
	calls [][]string
	fail  bool
}

func (f *fakeVMScript) run(_ context.Context, args ...string) ([]byte, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, args)
	if f.fail && args[1] == "Start" {
		return []byte("Hyper-V said no"), errors.New("exit status 1")
	}
	if args[1] == "Start" {
		return []byte("WARNING: noise\n{\"vm\":\"pfy-gz-" + args[5] + "\",\"gpu\":\"Test GPU\"}\n"), nil
	}
	return []byte("stopped"), nil
}

func gameAgent(t *testing.T, eligible bool, base string) (*Agent, *fakeVMScript) {
	a := newAgent(t, "http://127.0.0.1:1", true)
	if _, err := a.Store.Update(func(s *config.Settings) { s.GamezoneBaseVHD = base }); err != nil {
		t.Fatal(err)
	}
	a.gamezone = GamezoneCheck{Eligible: eligible}
	if !eligible {
		a.gamezone.Reasons = []string{"Windows Home can't host Gamezone."}
	}
	f := &fakeVMScript{}
	a.Games = &GameVMs{Run: f.run}
	return a, f
}

func call(a *Agent, typ, job string) map[string]any {
	return a.Handle(context.Background(), tunnel.Request{Type: typ, JobID: job})
}

func TestGameStartStop(t *testing.T) {
	a, f := gameAgent(t, true, `D:\Gamezone\base.vhdx`)
	res := call(a, "game.start", "gs-1")
	if res["ok"] != true {
		t.Fatalf("start failed: %v", res)
	}
	if vm := res["vm"].(map[string]any)["vm"]; vm != "pfy-gz-gs-1" {
		t.Fatalf("vm info not parsed from last line: %v", res["vm"])
	}
	if got := a.Heartbeat()["game_id"]; got != "gs-1" {
		t.Fatalf("heartbeat game_id = %v", got)
	}
	if res := call(a, "game.start", "gs-2"); res["ok"] != false || !strings.Contains(res["error"].(string), "already has a renter") {
		t.Fatalf("second session should be refused: %v", res)
	}
	if res := call(a, "job.start", "job-1"); res["ok"] != false {
		t.Fatalf("container job must be refused while a game runs: %v", res)
	}
	if res := call(a, "game.stop", "gs-1"); res["ok"] != true {
		t.Fatalf("stop failed: %v", res)
	}
	if a.Games.Active() != "" {
		t.Fatal("session still marked active after stop")
	}
	if len(f.calls) != 2 || f.calls[1][1] != "Stop" {
		t.Fatalf("unexpected script calls: %v", f.calls)
	}
}

func TestGameRefusedWhenNotEligibleOrNoImage(t *testing.T) {
	a, f := gameAgent(t, false, `D:\Gamezone\base.vhdx`)
	if res := call(a, "game.start", "gs-1"); res["ok"] != false || !strings.Contains(res["error"].(string), "Windows Home") {
		t.Fatalf("ineligible machine should refuse: %v", res)
	}
	b, _ := gameAgent(t, true, "")
	if res := call(b, "game.start", "gs-1"); res["ok"] != false || !strings.Contains(res["error"].(string), "base image") {
		t.Fatalf("missing base image should refuse: %v", res)
	}
	if res := call(b, "game.start", "../evil"); res["ok"] != false {
		t.Fatalf("bad job id should be refused: %v", res)
	}
	if len(f.calls) != 0 {
		t.Fatalf("script must not run when refused: %v", f.calls)
	}
}

func TestGameStartFailureCleansUp(t *testing.T) {
	a, f := gameAgent(t, true, `D:\Gamezone\base.vhdx`)
	f.fail = true
	if res := call(a, "game.start", "gs-1"); res["ok"] != false {
		t.Fatalf("expected failure: %v", res)
	}
	if a.Games.Active() != "" {
		t.Fatal("failed start left the machine marked busy")
	}
	if len(f.calls) != 2 || f.calls[1][1] != "Stop" {
		t.Fatalf("a failed start should run Stop to clean up: %v", f.calls)
	}
}

func TestBaseVHDValidation(t *testing.T) {
	s := config.Settings{BackendURL: "https://x", MemoryMB: 4096, CPUs: 2, DiskGB: 20, MaxGPUTempC: 80}
	for _, bad := range []string{"base.vhdx", `D:\Gamezone\base.iso`} {
		s.GamezoneBaseVHD = bad
		if s.Validate() == nil {
			t.Errorf("%q should be rejected", bad)
		}
	}
}
