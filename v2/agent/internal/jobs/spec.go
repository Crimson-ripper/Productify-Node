// Package jobs runs renter workloads in locked-down Docker containers.
//
// Everything that decides how a container is isolated lives in this file as
// plain functions returning argument lists, so it can be unit-tested without
// Docker. Arguments are passed to docker directly (never through a shell).
package jobs

import (
	"fmt"
	"strconv"

	"productifynode/internal/templates"
)

// Limits are the seller's resource caps for one job.
type Limits struct {
	MemoryMB  int
	CPUs      float64
	PIDs      int
	DiskGB    int
	ShareGPU  bool // seller allowed GPU passthrough
	GPUInDocker bool // the GPU check passed on this machine
}

// RunAs is the unprivileged user inside every job container.
const RunAs = "1000:1000"

// Network isolation: each job's own network is --internal (no route to the
// internet, the provider's LAN or the provider's computer). The only way out is
// the job's egress proxy container, which also sits on the shared EgressNetwork
// and only connects to public internet addresses (see internal/egress).
const (
	EgressNetwork = "productify-egress"
	EgressAlias   = "egress"
	EgressPort    = "3128"
	EgressBinary  = "productify-egress" // linux/amd64 binary shipped next to the agent
	egressMount   = "/opt/productify"
)

const (
	labelKey  = "productify.job"
	workdir   = "/workspace"
	namePref  = "productify-job-"
)

func ContainerName(jobID string) string { return namePref + jobID }
func VolumeName(jobID string) string    { return namePref + jobID }
func NetworkName(jobID string) string   { return namePref + jobID }
func ProxyName(jobID string) string     { return "productify-egress-" + jobID }

// NetworkCreateArgs creates an isolated bridge network for one job.
func NetworkCreateArgs(jobID string) []string {
	return []string{
		"network", "create",
		"--driver", "bridge",
		"--internal",
		"--label", labelKey + "=" + jobID,
		NetworkName(jobID),
	}
}

// EgressNetworkCreateArgs creates the shared bridge the egress proxies use to
// reach the internet. Containers on it can't talk to each other.
func EgressNetworkCreateArgs() []string {
	return []string{
		"network", "create",
		"--driver", "bridge",
		"--opt", "com.docker.network.bridge.enable_icc=false",
		"--label", labelKey + "=egress",
		EgressNetwork,
	}
}

// ProxyRunArgs starts the job's egress proxy from the agent's own binary,
// mounted read-only from binDir (the agent's install folder).
func ProxyRunArgs(jobID, image, binDir string) []string {
	return []string{
		"run", "--detach",
		"--name", ProxyName(jobID),
		"--label", labelKey + "=" + jobID,
		"--user", RunAs,
		"--cap-drop", "ALL",
		"--security-opt", "no-new-privileges",
		"--read-only",
		"--memory", "128m", "--memory-swap", "128m",
		"--cpus", "0.50",
		"--pids-limit", "64",
		"--network", EgressNetwork,
		"--mount", fmt.Sprintf("type=bind,src=%s,dst=%s,readonly", binDir, egressMount),
		"--restart", "no",
		"--entrypoint", egressMount + "/" + EgressBinary,
		image, ":" + EgressPort,
	}
}

// ProxyAttachArgs puts the proxy on the job's internal network as "egress".
func ProxyAttachArgs(jobID string) []string {
	return []string{"network", "connect", "--alias", EgressAlias, NetworkName(jobID), ProxyName(jobID)}
}

func proxyEnv() []string {
	u := "http://" + EgressAlias + ":" + EgressPort
	var out []string
	for _, k := range []string{"HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"} {
		out = append(out, "--env", k+"="+u)
	}
	return append(out, "--env", "NO_PROXY=localhost,127.0.0.1", "--env", "no_proxy=localhost,127.0.0.1")
}

// VolumeCreateArgs creates the job's scratch volume.
func VolumeCreateArgs(jobID string) []string {
	return []string{"volume", "create", "--label", labelKey + "=" + jobID, VolumeName(jobID)}
}

// PrepareVolumeArgs runs once, as root with only CAP_CHOWN, to hand the fresh
// volume to the unprivileged job user. It has no network.
func PrepareVolumeArgs(jobID string, t templates.Template) []string {
	return []string{
		"run", "--rm",
		"--network", "none",
		"--cap-drop", "ALL", "--cap-add", "CHOWN",
		"--security-opt", "no-new-privileges",
		"--mount", fmt.Sprintf("type=volume,src=%s,dst=%s", VolumeName(jobID), workdir),
		"--entrypoint", "chown",
		t.Image, RunAs, workdir,
	}
}

// RunArgs starts the long-lived job container. It idles; work arrives via exec.
func RunArgs(jobID string, t templates.Template, l Limits) []string {
	args := []string{
		"run", "--detach",
		"--name", ContainerName(jobID),
		"--label", labelKey + "=" + jobID,
		"--user", RunAs,
		"--workdir", workdir,
		"--env", "HOME=" + workdir, // the image's HOME is root-owned and read-only
		"--init",
		"--cap-drop", "ALL",
		"--security-opt", "no-new-privileges",
		"--read-only",
		"--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m",
		"--memory", strconv.Itoa(l.MemoryMB) + "m",
		"--memory-swap", strconv.Itoa(l.MemoryMB) + "m",
		"--cpus", strconv.FormatFloat(l.CPUs, 'f', 2, 64),
		"--pids-limit", strconv.Itoa(l.PIDs),
		"--network", NetworkName(jobID),
		"--mount", fmt.Sprintf("type=volume,src=%s,dst=%s", VolumeName(jobID), workdir),
		"--restart", "no",
	}
	args = append(args, proxyEnv()...)
	if t.GPU && l.ShareGPU && l.GPUInDocker {
		args = append(args, "--gpus", "all")
	}
	return append(args, "--entrypoint", "sleep", t.Image, "infinity")
}

// ExecArgs runs one command in the job container, killed after timeoutS seconds.
func ExecArgs(jobID string, argv []string, timeoutS int) []string {
	args := []string{"exec", "--user", RunAs, "--workdir", workdir, ContainerName(jobID),
		"timeout", "--signal=KILL", strconv.Itoa(timeoutS)}
	return append(args, argv...)
}

// Cleanup removes everything the job created. Errors are ignored by the caller
// because some objects may not exist if start failed halfway.
func CleanupArgs(jobID string) [][]string {
	return [][]string{
		{"rm", "--force", "--volumes", ContainerName(jobID)},
		{"rm", "--force", ProxyName(jobID)},
		{"volume", "rm", "--force", VolumeName(jobID)},
		{"network", "rm", NetworkName(jobID)},
	}
}

// Validate rejects limits that would make the container unsafe or useless.
func (l Limits) Validate() error {
	switch {
	case l.MemoryMB < 256:
		return fmt.Errorf("memory limit %d MB is below the 256 MB minimum", l.MemoryMB)
	case l.CPUs <= 0:
		return fmt.Errorf("cpu limit must be positive")
	case l.PIDs < 16:
		return fmt.Errorf("pids limit %d is below 16", l.PIDs)
	case l.DiskGB < 1:
		return fmt.Errorf("disk limit must be at least 1 GB")
	}
	return nil
}
