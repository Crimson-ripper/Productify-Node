//go:build windows

package ipc

import (
	"context"
	"net"
	"time"

	"github.com/Microsoft/go-winio"
)

// Listen creates the agent's pipe with the restricted ACL. It fails if
// another process already owns the name, so nothing can impersonate the agent
// while it runs.
func Listen(name string) (net.Listener, error) {
	return winio.ListenPipe(name, &winio.PipeConfig{SecurityDescriptor: SDDL, InputBufferSize: 64 << 10, OutputBufferSize: 64 << 10})
}

// Dial connects to the agent's pipe.
func Dial(name string) (net.Conn, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	return winio.DialPipeContext(ctx, name)
}
