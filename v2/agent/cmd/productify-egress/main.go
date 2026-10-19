// productify-egress is the per-job internet proxy. It runs inside a locked-down
// container (built for linux/amd64 and shipped next to the agent) and lets a
// renter job reach public internet addresses on ports 80/443 only.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"productifynode/internal/egress"
)

func main() {
	addr := ":3128"
	if len(os.Args) > 1 {
		addr = os.Args[1]
	}
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	log.Info("egress proxy listening", "addr", addr)
	if err := (&egress.Proxy{Log: log}).ListenAndServe(ctx, addr); err != nil {
		log.Error("egress proxy stopped", "err", err)
		os.Exit(1)
	}
}
