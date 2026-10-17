package jobs

import (
	"context"
	"errors"
	"strings"
	"testing"

	"productifynode/internal/templates"
)

var testLimits = Limits{MemoryMB: 2048, CPUs: 2, PIDs: 256, DiskGB: 10, ShareGPU: true, GPUInDocker: true}

func joined(a []string) string { return " " + strings.Join(a, " ") + " " }

func TestRunArgsAreLockedDown(t *testing.T) {
	tp, _ := templates.Lookup("python")
	got := joined(RunArgs("job-1", tp, testLimits))
	must := []string{
		" --user 1000:1000 ", " --cap-drop ALL ", " --security-opt no-new-privileges ", " --read-only ",
		" --memory 2048m ", " --memory-swap 2048m ", " --cpus 2.00 ", " --pids-limit 256 ",
		" --network productify-job-job-1 ", " --restart no ", " --init ",
	}
	for _, m := range must {
		if !strings.Contains(got, m) {
			t.Errorf("run args missing %q:\n%s", m, got)
		}
	}
	forbidden := []string{"--privileged", "--cap-add", " --pid ", "--pid=", "--ipc", "--userns","--network host", "type=bind", " -v ", "--volume", "docker.sock"}
	for _, f := range forbidden {
		if strings.Contains(got, f) {
			t.Errorf("run args must not contain %q:\n%s", f, got)
		}
	}
	if strings.Contains(got, "--gpus") {
		t.Errorf("python template must not request a GPU")
	}
	if !strings.HasSuffix(strings.TrimSpace(got), tp.Image+" infinity") {
		t.Errorf("image must be the pinned template image: %s", got)
	}
}

func TestGPUOnlyWhenAllowedAndAvailable(t *testing.T) {
	tp, _ := templates.Lookup("pytorch")
	if !strings.Contains(joined(RunArgs("j", tp, testLimits)), "--gpus all") {
		t.Error("pytorch with GPU sharing on should get --gpus")
	}
	off := testLimits
	off.ShareGPU = false
	if strings.Contains(joined(RunArgs("j", tp, off)), "--gpus") {
		t.Error("seller turned GPU sharing off")
	}
	noGPU := testLimits
	noGPU.GPUInDocker = false
	if strings.Contains(joined(RunArgs("j", tp, noGPU)), "--gpus") {
		t.Error("GPU check failed, must not pass --gpus")
	}
}

func TestPrepareVolumeOnlyChown(t *testing.T) {
	tp, _ := templates.Lookup("python")
	got := joined(PrepareVolumeArgs("j", tp))
	for _, m := range []string{" --network none ", " --cap-drop ALL --cap-add CHOWN ", " --entrypoint chown "} {
		if !strings.Contains(got, m) {
			t.Errorf("prepare args missing %q: %s", m, got)
		}
	}
}

func TestExecArgsHaveTimeout(t *testing.T) {
	got := joined(ExecArgs("j", []string{"python3", "-c", "print(1)"}, 30))
	if !strings.Contains(got, " --user 1000:1000 ") || !strings.Contains(got, " timeout --signal=KILL 30 python3 -c print(1) ") {
		t.Errorf("exec args: %s", got)
	}
}

// fakeDocker records calls and answers from a script.
type fakeDocker struct {
	calls   [][]string
	ready   bool
	failCmd string
}

func (f *fakeDocker) run(_ context.Context, args ...string) ([]byte, []byte, int, error) {
	f.calls = append(f.calls, args)
	if args[0] == "version" {
		if f.ready {
			return []byte("27.0"), nil, 0, nil
		}
		return nil, []byte("cannot connect"), 1, nil
	}
	if args[0] == f.failCmd {
		return nil, []byte("boom"), 1, nil
	}
	return []byte("ok"), nil, 0, nil
}

func newTestRunner(f *fakeDocker) *Runner {
	return NewRunner(f.run, func() Limits { return testLimits })
}

func TestStartRejectsBadInputWithoutTouchingDocker(t *testing.T) {
	f := &fakeDocker{ready: true}
	r := newTestRunner(f)
	if err := r.Start(context.Background(), "../escape", "python"); err == nil {
		t.Error("bad id accepted")
	}
	if err := r.Start(context.Background(), "ok-1", "ubuntu:latest"); err == nil {
		t.Error("non-allowlisted template accepted")
	}
	if len(f.calls) != 0 {
		t.Errorf("docker was called: %v", f.calls)
	}
}

func TestNoDockerMeansNoJob(t *testing.T) {
	f := &fakeDocker{ready: false}
	r := newTestRunner(f)
	err := r.Start(context.Background(), "ok-1", "python")
	if !errors.Is(err, ErrNoDocker) {
		t.Fatalf("want ErrNoDocker, got %v", err)
	}
	if _, err := r.Exec(context.Background(), "ok-1", []string{"id"}, 5); err == nil {
		t.Error("exec on a job that never started must fail")
	}
	for _, c := range f.calls {
		if c[0] != "version" {
			t.Errorf("unexpected docker call without docker: %v", c)
		}
	}
}

func TestStartFailureCleansUp(t *testing.T) {
	f := &fakeDocker{ready: true, failCmd: "run"}
	r := newTestRunner(f)
	if err := r.Start(context.Background(), "ok-1", "python"); err == nil {
		t.Fatal("expected failure")
	}
	if r.Count() != 0 {
		t.Error("failed job still tracked")
	}
	last := f.calls[len(f.calls)-1]
	if last[0] != "network" || last[1] != "rm" {
		t.Errorf("cleanup didn't run, last call %v", last)
	}
}

func TestStartExecStop(t *testing.T) {
	f := &fakeDocker{ready: true}
	r := newTestRunner(f)
	ctx := context.Background()
	if err := r.Start(ctx, "ok-1", "python"); err != nil {
		t.Fatal(err)
	}
	res, err := r.Exec(ctx, "ok-1", []string{"echo", "hi"}, 999)
	if err != nil || res.ExitCode != 0 {
		t.Fatalf("exec: %v %+v", err, res)
	}
	last := joined(f.calls[len(f.calls)-1])
	if !strings.Contains(last, " timeout --signal=KILL 120 ") {
		t.Errorf("timeout not clamped to 120: %s", last)
	}
	if n := r.StopAll(); n != 1 || r.Count() != 0 {
		t.Errorf("stop all: n=%d count=%d", n, r.Count())
	}
}
