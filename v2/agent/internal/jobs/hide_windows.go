//go:build windows

package jobs

import (
	"os/exec"
	"syscall"
)

// hideWindow stops a console window flashing up for each docker call.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000} // CREATE_NO_WINDOW
}
