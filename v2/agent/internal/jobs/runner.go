package jobs

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
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

// Docker runs a docker CLI command and returns stdout, stderr and the exit code.
// It is a variable so tests can replace it.
type Docker func(ctx context.Context, args ...string) (stdout, stderr []byte, code int, err error)

// Runner owns the jobs on this machine.
type Runner struct {
	docker Docker
	limits func() Limits

	mu   sync.Mutex
	jobs map[string]string // job id -> template name
}

func NewRunner(docker Docker, limits func() Limits) *Runner {
	return &Runner{docker: docker, limits: limits, jobs: map[string]string{}}
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
	r.mu.Lock()
	if _, exists := r.jobs[jobID]; exists {
		r.mu.Unlock()
		return fmt.Errorf("job %s is already running", jobID)
	}
	r.jobs[jobID] = templateName
	r.mu.Unlock()

	steps := [][]string{
		NetworkCreateArgs(jobID),
		VolumeCreateArgs(jobID),
		PrepareVolumeArgs(jobID, t),
		RunArgs(jobID, t, l),
	}
	for _, args := range steps {
		if _, stderr, code, err := r.docker(ctx, args...); err != nil || code != 0 {
			r.cleanup(jobID)
			return fmt.Errorf("docker %s failed: %s", args[0], firstLine(stderr, err))
		}
	}
	return nil
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
	_, ok := r.jobs[jobID]
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

// StopAll is the emergency stop: removes every job this agent started.
func (r *Runner) StopAll() int {
	r.mu.Lock()
	all := make([]string, 0, len(r.jobs))
	for id := range r.jobs {
		all = append(all, id)
	}
	r.mu.Unlock()
	for _, id := range all {
		r.cleanup(id)
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
