package jobs

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"productifynode/internal/ids"
	"productifynode/internal/templates"
)

// MaxOutput caps stdout and stderr returned for one exec.
const MaxOutput = 256 << 10

// MaxExecTimeout is the longest a single exec may run.
const MaxExecTimeout = 120

// ErrNoDocker is returned when Docker isn't usable. Jobs never fall back to
// running on the host.
var ErrNoDocker = errors.New("docker is not available on this machine")

// ErrBusy: one renter per machine, so renters never share a GPU.
var ErrBusy = errors.New("this machine is already in use by another renter")

// ErrNoIsolation: the egress proxy is missing, so a job's network couldn't be
// locked down. Jobs never start without it.
var ErrNoIsolation = errors.New("network isolation isn't available (the egress proxy is missing); reinstall Productify Node")

// Docker runs a docker CLI command and returns stdout, stderr and the exit code.
// It is a variable so tests can replace it.
type Docker func(ctx context.Context, args ...string) (stdout, stderr []byte, code int, err error)

// Runner owns the jobs on this machine.
type Runner struct {
	docker Docker
	limits func() Limits

	// EgressDir is the folder holding the linux egress proxy binary (the
	// agent's install folder). Required: no proxy, no job.
	EgressDir string
	// OnEnd is told about every job that ends on this machine for a reason
	// other than the backend asking (emergency stop, overheating, the
	// container dying, agent shutdown), so the backend can stop billing.
	OnEnd func(jobID, reason string)

	mu   sync.Mutex
	jobs map[string]*job
}

type job struct {
	template string
	ready    bool // container is up (false while starting)
}

func NewRunner(docker Docker, limits func() Limits) *Runner {
	return &Runner{docker: docker, limits: limits, jobs: map[string]*job{}}
}

// DockerReady reports whether the Docker engine answers.
func (r *Runner) DockerReady(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	_, _, code, err := r.docker(ctx, "version", "--format", "{{.Server.Version}}")
	return err == nil && code == 0
}

// GPUReady reports whether containers can see an NVIDIA GPU.
func (r *Runner) GPUReady(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	t, _ := templates.Lookup("python")
	_, _, code, err := r.docker(ctx, "run", "--rm", "--network", "none", "--gpus", "all", "--entrypoint", "true", t.Image)
	return err == nil && code == 0
}

// Count returns the number of running jobs.
func (r *Runner) Count() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.jobs)
}

// Start creates the job's network, volume and container.
func (r *Runner) Start(ctx context.Context, jobID, templateName string) error {
	if err := ids.ValidJobID(jobID); err != nil {
		return err
	}
	t, err := templates.Lookup(templateName)
	if err != nil {
		return err
	}
	l := r.limits()
	if err := l.Validate(); err != nil {
		return err
	}
	if !r.DockerReady(ctx) {
		return ErrNoDocker
	}
	if r.EgressDir == "" {
		return ErrNoIsolation
	}
	if fi, err := os.Stat(filepath.Join(r.EgressDir, EgressBinary)); err != nil || fi.IsDir() {
		return ErrNoIsolation
	}
	proxyImage, _ := templates.Lookup("python") // small image, also used for the GPU check
	r.mu.Lock()
	if _, exists := r.jobs[jobID]; exists {
		r.mu.Unlock()
		return fmt.Errorf("job %s is already running", jobID)
	}
	if len(r.jobs) > 0 {
		r.mu.Unlock()
		return ErrBusy
	}
	r.jobs[jobID] = &job{template: templateName}
	r.mu.Unlock()

	if _, _, code, err := r.docker(ctx, "network", "inspect", EgressNetwork); err != nil || code != 0 {
		if _, stderr, code, err := r.docker(ctx, EgressNetworkCreateArgs()...); (err != nil || code != 0) && !strings.Contains(string(stderr), "already exists") {
			r.cleanup(jobID)
			return fmt.Errorf("docker network create failed: %s", firstLine(stderr, err))
		}
	}
	steps := [][]string{
		NetworkCreateArgs(jobID),
		VolumeCreateArgs(jobID),
		PrepareVolumeArgs(jobID, t),
		ProxyRunArgs(jobID, proxyImage.Image, r.EgressDir),
		ProxyAttachArgs(jobID),
		RunArgs(jobID, t, l),
	}
	for _, args := range steps {
		if _, stderr, code, err := r.docker(ctx, args...); err != nil || code != 0 {
			r.cleanup(jobID)
			return fmt.Errorf("docker %s failed: %s", args[0], firstLine(stderr, err))
		}
	}
	r.mu.Lock()
	if j := r.jobs[jobID]; j != nil {
		j.ready = true
	}
	r.mu.Unlock()
	return nil
}

// JobIDs lists jobs whose container is up (sent to the backend so it can
// reconcile what it is billing for).
func (r *Runner) JobIDs() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]string, 0, len(r.jobs))
	for id, j := range r.jobs {
		if j.ready {
			out = append(out, id)
		}
	}
	return out
}

// Reap removes jobs whose container has stopped on its own (crashed, killed by
// Docker, machine resumed from sleep) and reports them.
func (r *Runner) Reap(ctx context.Context) {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	out, _, code, err := r.docker(ctx, "ps", "--filter", "label="+labelKey, "--format", "{{.Names}}")
	if err != nil || code != 0 {
		return // docker unavailable: try again next time rather than kill jobs
	}
	up := map[string]bool{}
	for _, n := range strings.Fields(string(out)) {
		up[n] = true
	}
	for _, id := range r.JobIDs() {
		if !up[ContainerName(id)] {
			r.cleanup(id)
			r.ended(id, "container_exited")
		}
	}
}

// RemoveOrphans deletes job containers left from before the agent started
// (for example after a power cut). Call once at startup.
func (r *Runner) RemoveOrphans(ctx context.Context) int {
	ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	out, _, code, err := r.docker(ctx, "ps", "--all", "--filter", "label="+labelKey, "--format", `{{.Label "`+labelKey+`"}}`)
	if err != nil || code != 0 {
		return 0
	}
	seen := map[string]bool{}
	for _, id := range strings.Fields(string(out)) {
		if id == "egress" || seen[id] || ids.ValidJobID(id) != nil {
			continue
		}
		seen[id] = true
		r.mu.Lock()
		_, tracked := r.jobs[id]
		r.mu.Unlock()
		if !tracked {
			r.cleanup(id)
		}
	}
	return len(seen)
}

func (r *Runner) ended(jobID, reason string) {
	if r.OnEnd != nil {
		r.OnEnd(jobID, reason)
	}
}

// ExecResult is what a renter sees from one command.
type ExecResult struct {
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exit_code"`
}

// Exec runs argv inside the job container.
func (r *Runner) Exec(ctx context.Context, jobID string, argv []string, timeoutS int) (ExecResult, error) {
	if err := ids.ValidJobID(jobID); err != nil {
		return ExecResult{}, err
	}
	if len(argv) == 0 {
		return ExecResult{}, errors.New("empty command")
	}
	r.mu.Lock()
	j, ok := r.jobs[jobID]
	ok = ok && j.ready
	r.mu.Unlock()
	if !ok {
		return ExecResult{}, fmt.Errorf("job %s is not running on this machine", jobID)
	}
	if timeoutS <= 0 || timeoutS > MaxExecTimeout {
		timeoutS = MaxExecTimeout
	}
	ctx, cancel := context.WithTimeout(ctx, time.Duration(timeoutS+10)*time.Second)
	defer cancel()
	stdout, stderr, code, err := r.docker(ctx, ExecArgs(jobID, argv, timeoutS)...)
	if err != nil && code == 0 {
		return ExecResult{}, err
	}
	return ExecResult{Stdout: truncate(stdout), Stderr: truncate(stderr), ExitCode: code}, nil
}

// Stop removes the job and everything it created.
func (r *Runner) Stop(jobID string) error {
	if err := ids.ValidJobID(jobID); err != nil {
		return err
	}
	r.cleanup(jobID)
	return nil
}

// StopAll removes every job this agent started and reports each one with
// reason (emergency_stop, overheated, agent_stopped).
func (r *Runner) StopAll(reason string) int {
	r.mu.Lock()
	all := make([]string, 0, len(r.jobs))
	for id := range r.jobs {
		all = append(all, id)
	}
	r.mu.Unlock()
	for _, id := range all {
		r.cleanup(id)
		r.ended(id, reason)
	}
	return len(all)
}

func (r *Runner) cleanup(jobID string) {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	for _, args := range CleanupArgs(jobID) {
		_, _, _, _ = r.docker(ctx, args...)
	}
	r.mu.Lock()
	delete(r.jobs, jobID)
	r.mu.Unlock()
}

// CLI returns a Docker func backed by the docker executable at path.
func CLI(path string) Docker {
	return func(ctx context.Context, args ...string) ([]byte, []byte, int, error) {
		cmd := exec.CommandContext(ctx, path, args...)
		hideWindow(cmd)
		var out, errb bytes.Buffer
		cmd.Stdout = &limitedWriter{buf: &out, max: MaxOutput + 1}
		cmd.Stderr = &limitedWriter{buf: &errb, max: MaxOutput + 1}
		err := cmd.Run()
		code := 0
		var ee *exec.ExitError
		if errors.As(err, &ee) {
			code, err = ee.ExitCode(), nil
		}
		return out.Bytes(), errb.Bytes(), code, err
	}
}

type limitedWriter struct {
	buf *bytes.Buffer
	max int
}

func (w *limitedWriter) Write(p []byte) (int, error) {
	if room := w.max - w.buf.Len(); room > 0 {
		if len(p) > room {
			w.buf.Write(p[:room])
		} else {
			w.buf.Write(p)
		}
	}
	return len(p), nil // keep draining so the process doesn't block
}

func truncate(b []byte) string {
	if len(b) > MaxOutput {
		return string(b[:MaxOutput]) + "\n[output truncated]"
	}
	return string(b)
}

func firstLine(stderr []byte, err error) string {
	if err != nil {
		return err.Error()
	}
	s := strings.TrimSpace(string(stderr))
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		s = s[:i]
	}
	return s
}
