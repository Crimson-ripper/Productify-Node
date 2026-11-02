package agent

import (
	"context"
	"strings"
	"testing"

	"productifynode/internal/tunnel"
)

func directAgent(t *testing.T) *Agent {
	a := newAgent(t, "http://127.0.0.1:1", true)
	a.Direct = &DirectJobs{}
	return a
}

func TestDirectJobLifecycle(t *testing.T) {
	a := directAgent(t)
	h := func(r tunnel.Request) map[string]any { return a.Handle(context.Background(), r) }

	if res := h(tunnel.Request{Type: "job.start", JobID: "inst-1"}); res["ok"] != true {
		t.Fatalf("start: %v", res)
	}
	if res := h(tunnel.Request{Type: "job.start", JobID: "inst-2"}); res["ok"] != false {
		t.Fatalf("second renter must be refused: %v", res)
	}
	res := h(tunnel.Request{Type: "job.exec", JobID: "inst-1", Argv: []string{"go", "env", "GOOS"}, TimeoutS: 30})
	if res["ok"] != true || strings.TrimSpace(res["stdout"].(string)) == "" || res["exit_code"] != 0 {
		t.Fatalf("exec: %v", res)
	}
	if res := h(tunnel.Request{Type: "job.exec", JobID: "inst-9", Argv: []string{"go", "version"}}); res["ok"] != false {
		t.Fatalf("exec for an unknown job must fail: %v", res)
	}
	ids := a.Heartbeat()["job_ids"].([]string)
	if len(ids) != 1 || ids[0] != "inst-1" {
		t.Fatalf("heartbeat job_ids = %v", ids)
	}
	if a.Hello()["isolation"] != "partner-instance" {
		t.Fatal("hello should report partner-instance isolation in direct mode")
	}
	h(tunnel.Request{Type: "job.stop", JobID: "inst-1"})
	if len(a.Direct.JobIDs()) != 0 {
		t.Fatal("stop should clear the job")
	}
}

func TestDirectExitCode(t *testing.T) {
	a := directAgent(t)
	_ = a.Direct.Start("inst-1")
	_, _, code, err := a.Direct.Exec(context.Background(), "inst-1", []string{"go", "not-a-command"}, 30)
	if err != nil || code == 0 {
		t.Fatalf("want a non-zero exit code, got %d %v", code, err)
	}
}
