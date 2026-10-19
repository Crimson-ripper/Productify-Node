package agent

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/coder/websocket"

	"productifynode/internal/config"
	"productifynode/internal/jobs"
	"productifynode/internal/tunnel"
)

type fakeGPU struct{ temp int }

func (f *fakeGPU) Name() string       { return "Test GPU" }
func (f *fakeGPU) VRAMMB() int        { return 8192 }
func (f *fakeGPU) Temp() (int, bool)  { return f.temp, true }

func fakeDocker(ctx context.Context, args ...string) ([]byte, []byte, int, error) {
	if args[0] == "exec" {
		return []byte("hello from container\n"), nil, 0, nil
	}
	return []byte("ok"), nil, 0, nil
}

func newAgent(t *testing.T, backend string, live bool) *Agent {
	t.Helper()
	st, err := config.Open(filepath.Join(t.TempDir(), "node.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.Update(func(s *config.Settings) {
		s.BackendURL, s.RentalID, s.Token, s.Live = backend, "r-abc123def4", "ptok_0123456789abcdef", live
	}); err != nil {
		t.Fatal(err)
	}
	a := &Agent{Store: st, GPU: &fakeGPU{temp: 50}, Log: slog.New(slog.NewTextHandler(io.Discard, nil))}
	a.Runner = jobs.NewRunner(fakeDocker, func() jobs.Limits { return st.Get().Limits(false) })
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, jobs.EgressBinary), []byte("bin"), 0o755); err != nil {
		t.Fatal(err)
	}
	a.Runner.EgressDir = dir
	return a
}

// backend is a tiny stand-in for /ws/node/v1 that sends a script of requests.
func backend(t *testing.T, script []map[string]any, results chan<- map[string]any) *httptest.Server {
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != tunnel.Path || r.Header.Get("Authorization") != "Bearer ptok_0123456789abcdef" || r.Header.Get("X-Rental-Id") != "r-abc123def4" {
			http.Error(w, "nope", http.StatusUnauthorized)
			return
		}
		c, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer c.CloseNow()
		ctx := r.Context()
		read := func() map[string]any {
			_, b, err := c.Read(ctx)
			if err != nil {
				return nil
			}
			var m map[string]any
			_ = json.Unmarshal(b, &m)
			return m
		}
		results <- read() // hello
		for _, req := range script {
			b, _ := json.Marshal(req)
			if err := c.Write(ctx, websocket.MessageText, b); err != nil {
				return
			}
			for {
				m := read()
				if m == nil {
					return
				}
				if m["type"] == "result" {
					results <- m
					break
				}
			}
		}
		<-ctx.Done()
	}))
}

func TestEndToEndJobOverTunnel(t *testing.T) {
	results := make(chan map[string]any, 10)
	srv := backend(t, []map[string]any{
		{"type": "ping", "id": "1"},
		{"type": "job.start", "id": "2", "job_id": "inst-1", "template": "python"},
		{"type": "job.exec", "id": "3", "job_id": "inst-1", "python": "print('hi')"},
		{"type": "job.start", "id": "4", "job_id": "../x", "template": "python"},
		{"type": "job.start", "id": "5", "job_id": "inst-2", "template": "alpine:latest"},
		{"type": "job.stop", "id": "6", "job_id": "inst-1"},
		{"type": "rm -rf", "id": "7"},
	}, results)
	defer srv.Close()

	a := newAgent(t, srv.URL, true)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	go a.Run(ctx)

	hello := <-results
	if hello["type"] != "hello" || hello["gpu"] != "Test GPU" || hello["live"] != true {
		t.Fatalf("hello: %v", hello)
	}
	want := []struct {
		ok  bool
		key string
	}{{true, ""}, {true, "container"}, {true, "stdout"}, {false, ""}, {false, ""}, {true, ""}, {false, ""}}
	for i, w := range want {
		select {
		case r := <-results:
			if r["ok"] != w.ok {
				t.Errorf("step %d: ok=%v want %v (%v)", i+1, r["ok"], w.ok, r)
			}
			if w.key != "" && r[w.key] == nil {
				t.Errorf("step %d: missing %s (%v)", i+1, w.key, r)
			}
		case <-ctx.Done():
			t.Fatalf("timed out at step %d", i+1)
		}
	}
}

func TestPausedMachineRefusesJobs(t *testing.T) {
	results := make(chan map[string]any, 4)
	srv := backend(t, []map[string]any{{"type": "job.start", "id": "1", "job_id": "inst-1", "template": "python"}}, results)
	defer srv.Close()
	a := newAgent(t, srv.URL, false)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	go a.Run(ctx)
	<-results // hello
	r := <-results
	if r["ok"] != false || a.Runner.Count() != 0 {
		t.Errorf("paused node accepted a job: %v", r)
	}
}

func TestRejectedTokenStopsReconnecting(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "bad token", http.StatusUnauthorized)
	}))
	defer srv.Close()
	a := newAgent(t, srv.URL, true)
	c := &tunnel.Client{BackendURL: srv.URL, RentalID: "r-abc123def4", Token: "ptok_bad", Handler: a, Log: a.Log}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := c.Run(ctx); !errors.Is(err, tunnel.ErrUnauthorized) {
		t.Errorf("want ErrUnauthorized, got %v", err)
	}
}

func TestThermalGuard(t *testing.T) {
	a := newAgent(t, "https://example.invalid", true)
	a.mu.Lock()
	a.dockerReady = true
	a.mu.Unlock()
	if err := a.Runner.Start(context.Background(), "inst-1", "python"); err != nil {
		t.Fatal(err)
	}
	gpu := a.GPU.(*fakeGPU)
	gpu.temp = 90 // ceiling is 80
	now := time.Now()
	a.CheckThermal(now)
	if a.Runner.Count() != 1 {
		t.Fatal("must tolerate a short spike")
	}
	a.CheckThermal(now.Add(31 * time.Second))
	if a.Runner.Count() != 0 || a.Status().PausedReason != "thermal" || a.Status().Live {
		t.Fatalf("hot GPU not handled: %+v", a.Status())
	}
	if r := a.Handle(context.Background(), tunnel.Request{Type: "job.start", ID: "x", JobID: "inst-2", Template: "python"}); r["ok"] != false {
		t.Error("accepted a job while too hot")
	}
	gpu.temp = 75
	a.CheckThermal(now.Add(40 * time.Second))
	if a.Status().PausedReason != "thermal" {
		t.Error("resumed before cooling 10 °C below the ceiling")
	}
	gpu.temp = 69
	a.CheckThermal(now.Add(50 * time.Second))
	if a.Status().PausedReason != "" || !a.Status().Live {
		t.Errorf("did not resume after cooling: %+v", a.Status())
	}
}
