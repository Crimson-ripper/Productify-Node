// Package agent connects the tunnel, the job runner, the seller's settings and
// the thermal guard.
package agent

import (
	"context"
	"log/slog"
	"runtime"
	"sync"
	"time"

	"productifynode/internal/config"
	"productifynode/internal/jobs"
	"productifynode/internal/tunnel"
)

const Version = "2.0.0-dev"

// GPUInfo is read from the machine; Temp returns ok=false when unknown.
type GPUInfo interface {
	Name() string
	VRAMMB() int
	Temp() (celsius int, ok bool)
}

type Agent struct {
	Store  *config.Store
	Runner *jobs.Runner
	GPU    GPUInfo
	Log    *slog.Logger

	mu            sync.Mutex
	dockerReady   bool
	gpuInDocker   bool
	pausedReason  string // "", "seller", "thermal"
	hotSince      time.Time
	events        func(map[string]any) // set by Run to send tunnel events
}

// Probe refreshes Docker/GPU readiness. Call at start and periodically.
func (a *Agent) Probe(ctx context.Context) {
	ready := a.Runner.DockerReady(ctx)
	gpu := false
	if ready && a.Store.Get().ShareGPU {
		gpu = a.Runner.GPUReady(ctx)
	}
	a.mu.Lock()
	a.dockerReady, a.gpuInDocker = ready, gpu
	a.mu.Unlock()
}

// Status is shown in the desktop app.
type Status struct {
	Paired       bool   `json:"paired"`
	Live         bool   `json:"live"`
	PausedReason string `json:"paused_reason"`
	Docker       bool   `json:"docker"`
	GPUInDocker  bool   `json:"gpu_in_docker"`
	Jobs         int    `json:"jobs"`
	GPU          string `json:"gpu"`
	GPUTempC     *int   `json:"gpu_temp_c"`
}

func (a *Agent) Status() Status {
	s := a.Store.Get()
	a.mu.Lock()
	defer a.mu.Unlock()
	st := Status{Paired: s.Paired(), Live: s.Live && a.pausedReason == "", PausedReason: a.pausedReason,
		Docker: a.dockerReady, GPUInDocker: a.gpuInDocker, Jobs: a.Runner.Count(), GPU: a.GPU.Name()}
	if t, ok := a.GPU.Temp(); ok {
		st.GPUTempC = &t
	}
	return st
}

// ---- tunnel.Handler ----

func (a *Agent) Hello() map[string]any {
	s := a.Store.Get()
	st := a.Status()
	return map[string]any{
		"agent_version": Version, "node_id": s.NodeID, "os": runtime.GOOS,
		"gpu": a.GPU.Name(), "vram_mb": a.GPU.VRAMMB(), "cpu_cores": runtime.NumCPU(),
		"docker": st.Docker, "gpu_in_docker": st.GPUInDocker, "live": st.Live,
	}
}

func (a *Agent) Heartbeat() map[string]any {
	st := a.Status()
	m := map[string]any{"live": st.Live, "jobs": st.Jobs, "paused_reason": st.PausedReason}
	if st.GPUTempC != nil {
		m["gpu_temp_c"] = *st.GPUTempC
	}
	return m
}

func fail(msg string) map[string]any { return map[string]any{"ok": false, "error": msg} }

func (a *Agent) Handle(ctx context.Context, req tunnel.Request) map[string]any {
	switch req.Type {
	case "ping":
		return map[string]any{"ok": true}
	case "job.start":
		st := a.Status()
		if !st.Live {
			return fail("this machine is paused by its owner")
		}
		if !st.Docker {
			return fail(jobs.ErrNoDocker.Error())
		}
		if err := a.Runner.Start(ctx, req.JobID, req.Template); err != nil {
			return fail(err.Error())
		}
		a.Log.Info("job started", "job", req.JobID, "template", req.Template)
		return map[string]any{"ok": true, "container": jobs.ContainerName(req.JobID)}
	case "job.exec":
		argv := req.Argv
		if req.Python != "" {
			argv = []string{"python3", "-c", req.Python}
		}
		res, err := a.Runner.Exec(ctx, req.JobID, argv, req.TimeoutS)
		if err != nil {
			return fail(err.Error())
		}
		return map[string]any{"ok": true, "stdout": res.Stdout, "stderr": res.Stderr, "exit_code": res.ExitCode}
	case "job.stop":
		if err := a.Runner.Stop(req.JobID); err != nil {
			return fail(err.Error())
		}
		a.Log.Info("job stopped", "job", req.JobID)
		return map[string]any{"ok": true}
	}
	return fail("unsupported")
}

// ---- seller controls (called from the desktop app via IPC) ----

// SetLive turns renting on or off. Turning it off doesn't kill running jobs.
func (a *Agent) SetLive(live bool) error {
	_, err := a.Store.Update(func(s *config.Settings) { s.Live = live })
	if err == nil && live {
		a.mu.Lock()
		if a.pausedReason == "seller" {
			a.pausedReason = ""
		}
		a.mu.Unlock()
	}
	return err
}

// EmergencyStop kills every job and pauses the node.
func (a *Agent) EmergencyStop() int {
	n := a.Runner.StopAll()
	_ = a.SetLive(false)
	a.Log.Warn("emergency stop", "jobs_killed", n)
	return n
}

// ---- thermal guard ----

// CheckThermal is called every few seconds. If the GPU stays over the seller's
// ceiling for 30 s, every job is stopped and the node pauses until it cools
// 10 °C below the ceiling.
func (a *Agent) CheckThermal(now time.Time) {
	t, ok := a.GPU.Temp()
	if !ok {
		return
	}
	max := a.Store.Get().MaxGPUTempC
	a.mu.Lock()
	defer a.mu.Unlock()
	switch {
	case a.pausedReason == "thermal":
		if t <= max-10 {
			a.pausedReason = ""
			a.hotSince = time.Time{}
			a.Log.Info("GPU cooled down; accepting jobs again", "temp_c", t)
		}
	case t > max:
		if a.hotSince.IsZero() {
			a.hotSince = now
		} else if now.Sub(a.hotSince) >= 30*time.Second {
			a.pausedReason = "thermal"
			a.mu.Unlock()
			n := a.Runner.StopAll()
			a.mu.Lock()
			a.Log.Error("GPU too hot; stopped all jobs", "temp_c", t, "max_c", max, "jobs_killed", n)
			if a.events != nil {
				a.events(map[string]any{"type": "event", "kind": "killed_thermal", "temp_c": t})
			}
		}
	default:
		a.hotSince = time.Time{}
	}
}

// Run starts the background loops and the tunnel. It returns when ctx ends or
// the pairing is rejected.
func (a *Agent) Run(ctx context.Context) error {
	a.Probe(ctx)
	go func() {
		thermal := time.NewTicker(5 * time.Second)
		probe := time.NewTicker(2 * time.Minute)
		defer thermal.Stop()
		defer probe.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case now := <-thermal.C:
				a.CheckThermal(now)
			case <-probe.C:
				a.Probe(ctx)
			}
		}
	}()

	for {
		s := a.Store.Get()
		if !s.Paired() {
			a.Log.Info("not paired yet; waiting")
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(10 * time.Second):
				continue
			}
		}
		c := &tunnel.Client{BackendURL: s.BackendURL, RentalID: s.RentalID, Token: s.Token, Handler: a, Log: a.Log}
		a.mu.Lock()
		a.events = func(m map[string]any) { _ = c.Send(context.Background(), m) }
		a.mu.Unlock()
		err := c.Run(ctx)
		if ctx.Err() != nil {
			return ctx.Err()
		}
		// Rejected pairing: wait for the seller to pair again (settings change).
		a.Log.Error("tunnel stopped", "err", err)
		for a.Store.Get().Token == s.Token {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(10 * time.Second):
			}
		}
	}
}
