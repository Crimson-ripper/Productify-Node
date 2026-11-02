package agent

import (
	"bytes"
	"context"
	"errors"
	"os/exec"
	"sync"
	"time"

	"productifynode/internal/ids"
)

// DirectJobs is "direct mode": the agent runs inside a rented partner machine (e.g. a Vast.ai
// instance) that already is the renter's isolated container. There is no Docker inside it, so
// a job is just this machine: commands run here, and the backend destroys the whole machine
// when the renter stops. One job per machine.
type DirectJobs struct {
	Shell string // default /bin/sh

	mu  sync.Mutex
	job string
}

var errDirectBusy = errors.New("this machine already has a renter")

func (d *DirectJobs) Start(jobID string) error {
	if err := ids.ValidJobID(jobID); err != nil {
		return err
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.job != "" && d.job != jobID {
		return errDirectBusy
	}
	d.job = jobID
	return nil
}

func (d *DirectJobs) Stop(jobID string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.job == jobID {
		d.job = ""
	}
}

func (d *DirectJobs) JobIDs() []string {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.job == "" {
		return []string{}
	}
	return []string{d.job}
}

func (d *DirectJobs) has(jobID string) bool {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.job != "" && d.job == jobID
}

// Exec runs argv on this machine with a timeout and returns its output, like Runner.Exec.
func (d *DirectJobs) Exec(ctx context.Context, jobID string, argv []string, timeoutS int) (stdout, stderr string, code int, err error) {
	if !d.has(jobID) {
		return "", "", 0, errors.New("no such job on this machine")
	}
	if len(argv) == 0 {
		return "", "", 0, errors.New("nothing to run")
	}
	if timeoutS <= 0 || timeoutS > 600 {
		timeoutS = 60
	}
	ctx, cancel := context.WithTimeout(ctx, time.Duration(timeoutS)*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	cmd.Dir = "/workspace"
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	runErr := cmd.Run()
	code = 0
	if runErr != nil {
		var ee *exec.ExitError
		if errors.As(runErr, &ee) {
			code = ee.ExitCode()
		} else if ctx.Err() != nil {
			return out.String(), errb.String(), -1, errors.New("the command took too long and was stopped")
		} else {
			// e.g. /workspace missing: retry from the current directory
			cmd2 := exec.CommandContext(ctx, argv[0], argv[1:]...)
			out.Reset()
			errb.Reset()
			cmd2.Stdout, cmd2.Stderr = &out, &errb
			if err2 := cmd2.Run(); err2 != nil {
				if errors.As(err2, &ee) {
					code = ee.ExitCode()
				} else {
					return "", "", 0, err2
				}
			}
		}
	}
	return out.String(), errb.String(), code, nil
}

// directHandle serves job.* requests in direct mode. ok=false means "not a direct-mode request".
func (a *Agent) directHandle(ctx context.Context, typ, jobID string, argv []string, python string, timeoutS int) (map[string]any, bool) {
	switch typ {
	case "job.start":
		if err := a.Direct.Start(jobID); err != nil {
			return fail(err.Error()), true
		}
		a.Log.Info("direct job started", "job", jobID)
		return map[string]any{"ok": true, "container": "direct"}, true
	case "job.exec":
		if python != "" {
			argv = []string{"python3", "-c", python}
		}
		so, se, code, err := a.Direct.Exec(ctx, jobID, argv, timeoutS)
		if err != nil {
			return fail(err.Error()), true
		}
		return map[string]any{"ok": true, "stdout": so, "stderr": se, "exit_code": code}, true
	case "job.stop":
		a.Direct.Stop(jobID)
		return map[string]any{"ok": true}, true
	}
	return nil, false
}
