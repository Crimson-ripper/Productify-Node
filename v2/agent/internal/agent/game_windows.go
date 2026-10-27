//go:build windows

package agent

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

func newGameVMs(script string) *GameVMs {
	if _, err := os.Stat(script); err != nil {
		return nil
	}
	return &GameVMs{Run: func(ctx context.Context, args ...string) ([]byte, error) {
		ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
		defer cancel()
		cmd := exec.CommandContext(ctx, "powershell.exe", append([]string{"-NoProfile", "-NonInteractive",
			"-ExecutionPolicy", "Bypass", "-File", script}, args...)...)
		hideWindow(cmd)
		out, err := cmd.Output()
		if err != nil {
			msg := strings.TrimSpace(string(out))
			if ee, ok := err.(*exec.ExitError); ok && len(ee.Stderr) > 0 {
				msg = strings.TrimSpace(string(ee.Stderr))
			}
			if len(msg) > 300 {
				msg = msg[len(msg)-300:]
			}
			return out, fmt.Errorf("%v: %s", err, msg)
		}
		return out, nil
	}}
}
