//go:build !windows

package jobs

import "os/exec"

func hideWindow(*exec.Cmd) {}
