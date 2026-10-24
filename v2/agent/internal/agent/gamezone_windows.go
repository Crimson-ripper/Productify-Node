//go:build windows

package agent

import (
	"context"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"golang.org/x/sys/windows/registry"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

// CheckGamezone reads the Windows edition, the Hyper-V service state and GPU partition support.
// It runs PowerShell once (a few seconds), so callers cache the result.
func CheckGamezone(ctx context.Context) GamezoneCheck {
	name, id := windowsEdition()
	hv := hyperVRunning()
	gpup := false
	if hv {
		gpup = partitionableGPU(ctx)
	}
	return evaluateGamezone(runtime.GOOS, name, id, hv, gpup)
}

func windowsEdition() (name, id string) {
	k, err := registry.OpenKey(registry.LOCAL_MACHINE, `SOFTWARE\Microsoft\Windows NT\CurrentVersion`, registry.QUERY_VALUE)
	if err != nil {
		return "", ""
	}
	defer k.Close()
	id, _, _ = k.GetStringValue("EditionID")
	name, _, _ = k.GetStringValue("ProductName")
	// Windows 11 still says "Windows 10 ..." in ProductName; build 22000+ is Windows 11.
	if build, _, err := k.GetStringValue("CurrentBuildNumber"); err == nil && build >= "22000" && len(build) == 5 {
		name = strings.Replace(name, "Windows 10", "Windows 11", 1)
	}
	return strings.TrimSpace(name), strings.TrimSpace(id)
}

func hyperVRunning() bool {
	m, err := mgr.Connect()
	if err != nil {
		return false
	}
	defer m.Disconnect()
	s, err := m.OpenService("vmms") // Hyper-V Virtual Machine Management
	if err != nil {
		return false
	}
	defer s.Close()
	st, err := s.Query()
	return err == nil && st.State == svc.Running
}

func partitionableGPU(ctx context.Context) bool {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
		"(Get-VMHostPartitionableGpu -ErrorAction Stop | Measure-Object).Count")
	hideWindow(cmd)
	out, err := cmd.Output()
	if err != nil {
		return false
	}
	n := strings.TrimSpace(string(out))
	return n != "" && n != "0"
}
