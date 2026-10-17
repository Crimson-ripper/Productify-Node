//go:build windows

package config

import (
	"os/exec"
	"syscall"
)

// restrict limits the settings file (it holds the pairing token) to SYSTEM and
// Administrators, removing inherited access for ordinary users.
func restrict(path string) {
	cmd := exec.Command("icacls", path, "/inheritance:r", "/grant:r", "*S-1-5-18:F", "*S-1-5-32-544:F")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
	_ = cmd.Run()
}
