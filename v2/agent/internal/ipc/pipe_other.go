//go:build !windows

package ipc

import (
	"net"
	"os"
	"path/filepath"
)

// On Linux/macOS the control channel is a unix socket readable only by its owner.
func sockPath(name string) string { return filepath.Join(os.TempDir(), filepath.Base(name)+".sock") }

func Listen(name string) (net.Listener, error) {
	p := sockPath(name)
	_ = os.Remove(p)
	l, err := net.Listen("unix", p)
	if err == nil {
		_ = os.Chmod(p, 0o600)
	}
	return l, err
}

func Dial(name string) (net.Conn, error) { return net.Dial("unix", sockPath(name)) }
