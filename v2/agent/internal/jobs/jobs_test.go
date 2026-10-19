package jobs

import (
	"context"
	"errors"
	"os"
	"path/filepath"
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
	r := NewRunner(f.run, func() Limits { return testLimits })
	r.EgressDir = fakeEgressDir
	return r
}

var fakeEgressDir = func() string {
	d, _ := os.MkdirTemp("", "egress")
	_ = os.WriteFile(filepath.Join(d, EgressBinary), []byte("bin"), 0o755)
	return d
}()

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
	if n := r.StopAll("emergency_stop"); n != 1 || r.Count() != 0 {
		t.Errorf("stop all: n=%d count=%d", n, r.Count())
	}
}

func TestJobNetworkIsInternalWithEgressProxy(t *testing.T) {
	if !strings.Contains(joined(NetworkCreateArgs("j")), " --internal ") {
		t.Error("job network must be --internal (no route to host, LAN or internet)")
	}
	tp, _ := templates.Lookup("python")
	run := joined(RunArgs("j", tp, testLimits))
	for _, m := range []string{" --env HTTPS_PROXY=http://egress:3128 ", " --env HTTP_PROXY=http://egress:3128 ", " --env https_proxy=http://egress:3128 "} {
		if !strings.Contains(run, m) {
			t.Errorf("job missing proxy env %q", m)
		}
	}
	px := joined(ProxyRunArgs("j", tp.Image, `C:\Program Files\Productify Node`))
	for _, m := range []string{" --user 1000:1000 ", " --cap-drop ALL ", " --read-only ", " --network productify-egress ",
		` type=bind,src=C:\Program Files\Productify Node,dst=/opt/productify,readonly `, " --entrypoint /opt/productify/productify-egress "} {
		if !strings.Contains(px, m) {
			t.Errorf("proxy args missing %q:\n%s", m, px)
		}
	}
	for _, f := range []string{"--privileged", "--cap-add", "--network host", "docker.sock"} {
		if strings.Contains(px, f) {
			t.Errorf("proxy args must not contain %q", f)
		}
	}
	if !strings.Contains(joined(EgressNetworkCreateArgs()), " com.docker.network.bridge.enable_icc=false ") {
		t.Error("egress network must block container-to-container traffic")
	}
}

func TestStartOrderAndProxy(t *testing.T) {
	f := &fakeDocker{ready: true}
	r := newTestRunner(f)
	if err := r.Start(context.Background(), "ok-1", "python"); err != nil {
		t.Fatal(err)
	}
	var seq []string
	for _, c := range f.calls {
		if c[0] != "version" {
			seq = append(seq, c[0]+" "+c[1])
		}
	}
	got := strings.Join(seq, " | ")
	want := "network inspect | network create | volume create | run --rm | run --detach | network connect | run --detach"
	if got != want {
		t.Errorf("start sequence:\n got %s\nwant %s", got, want)
	}
}

func TestNoEgressBinaryMeansNoJob(t *testing.T) {
	f := &fakeDocker{ready: true}
	r := NewRunner(f.run, func() Limits { return testLimits })
	if err := r.Start(context.Background(), "ok-1", "python"); !errors.Is(err, ErrNoIsolation) {
		t.Fatalf("no egress dir: want ErrNoIsolation, got %v", err)
	}
	r.EgressDir = t.TempDir() // folder exists, binary doesn't
	if err := r.Start(context.Background(), "ok-1", "python"); !errors.Is(err, ErrNoIsolation) {
		t.Fatalf("missing binary: want ErrNoIsolation, got %v", err)
	}
	for _, c := range f.calls {
		if c[0] == "run" {
			t.Fatalf("container started without isolation: %v", c)
		}
	}
}

func TestOneRenterPerMachine(t *testing.T) {
	f := &fakeDocker{ready: true}
	r := newTestRunner(f)
	if err := r.Start(context.Background(), "ok-1", "pytorch"); err != nil {
		t.Fatal(err)
	}
	if err := r.Start(context.Background(), "ok-2", "python"); !errors.Is(err, ErrBusy) {
		t.Fatalf("second job: want ErrBusy, got %v", err)
	}
	_ = r.Stop("ok-1")
	if err := r.Start(context.Background(), "ok-2", "python"); err != nil {
		t.Fatalf("after stop the machine is free again: %v", err)
	}
}

func TestEndsAreReported(t *testing.T) {
	f := &fakeDocker{ready: true}
	r := newTestRunner(f)
	var ended []string
	r.OnEnd = func(id, reason string) { ended = append(ended, id+":"+reason) }
	ctx := context.Background()
	_ = r.Start(ctx, "ok-1", "python")
	_ = r.Stop("ok-1") // backend asked: no report needed
	_ = r.Start(ctx, "ok-2", "python")
	r.StopAll("emergency_stop")
	if strings.Join(ended, ",") != "ok-2:emergency_stop" {
		t.Fatalf("ended = %v", ended)
	}
}

// psDocker answers "docker ps" with a fixed list of container names.
type psDocker struct {
	fakeDocker
	ps string
}

func (p *psDocker) run(ctx context.Context, args ...string) ([]byte, []byte, int, error) {
	if args[0] == "ps" {
		p.calls = append(p.calls, args)
		return []byte(p.ps), nil, 0, nil
	}
	return p.fakeDocker.run(ctx, args...)
}

func TestReapReportsDeadContainers(t *testing.T) {
	p := &psDocker{fakeDocker: fakeDocker{ready: true}}
	r := NewRunner(p.run, func() Limits { return testLimits })
	r.EgressDir = fakeEgressDir
	var ended []string
	r.OnEnd = func(id, reason string) { ended = append(ended, id+":"+reason) }
	_ = r.Start(context.Background(), "ok-1", "python")
	p.ps = ContainerName("ok-1") + "\n" + ProxyName("ok-1") + "\n"
	r.Reap(context.Background())
	if len(ended) != 0 || r.Count() != 1 {
		t.Fatalf("healthy job reaped: %v", ended)
	}
	p.ps = ""
	r.Reap(context.Background())
	if strings.Join(ended, ",") != "ok-1:container_exited" || r.Count() != 0 {
		t.Fatalf("dead job not reaped: %v count=%d", ended, r.Count())
	}
	if ids := r.JobIDs(); len(ids) != 0 {
		t.Fatalf("job ids after reap: %v", ids)
	}
}

func TestRemoveOrphans(t *testing.T) {
	p := &psDocker{fakeDocker: fakeDocker{ready: true}, ps: "old-1\nold-1\negress\n../bad\n"}
	r := NewRunner(p.run, func() Limits { return testLimits })
	if n := r.RemoveOrphans(context.Background()); n != 1 {
		t.Fatalf("orphans = %d", n)
	}
	var removed []string
	for _, c := range p.calls {
		if c[0] == "rm" {
			removed = append(removed, c[len(c)-1])
		}
	}
	if strings.Join(removed, ",") != ContainerName("old-1")+","+ProxyName("old-1") {
		t.Fatalf("removed %v", removed)
	}
}
