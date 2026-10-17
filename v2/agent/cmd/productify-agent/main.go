// productify-agent runs on a seller's machine and serves their Productify GPU listing.
//
//	productify-agent pair --rental r-xxxxxxxxxx --token ptok_xxxxxxxxxxxxxxxx
//	productify-agent live on|off
//	productify-agent status
//	productify-agent run            # foreground; the Windows service runs this
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"os/signal"
	"strings"

	"productifynode/internal/agent"
	"productifynode/internal/config"
	"productifynode/internal/jobs"
)

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	cfgPath := os.Getenv("PRODUCTIFY_NODE_CONFIG")
	if cfgPath == "" {
		cfgPath = config.DefaultPath()
	}
	store, err := config.Open(cfgPath)
	if err != nil {
		fatal(err)
	}

	switch os.Args[1] {
	case "pair":
		fs := flag.NewFlagSet("pair", flag.ExitOnError)
		rental := fs.String("rental", "", "listing id from Seller studio (r-…)")
		token := fs.String("token", "", "pairing token from Seller studio (ptok_…)")
		backend := fs.String("backend", "", "backend URL (default: productifynow)")
		_ = fs.Parse(os.Args[2:])
		_, err := store.Update(func(s *config.Settings) {
			s.RentalID, s.Token = strings.TrimSpace(*rental), strings.TrimSpace(*token)
			if *backend != "" {
				s.BackendURL = strings.TrimRight(*backend, "/")
			}
		})
		if err != nil {
			fatal(err)
		}
		fmt.Println("Paired. Run `productify-agent live on` when you're ready to accept renters.")
	case "live":
		if len(os.Args) < 3 || (os.Args[2] != "on" && os.Args[2] != "off") {
			usage()
		}
		if _, err := store.Update(func(s *config.Settings) { s.Live = os.Args[2] == "on" }); err != nil {
			fatal(err)
		}
		fmt.Println("Renting is", os.Args[2])
	case "status":
		a := newAgent(store)
		a.Probe(context.Background())
		b, _ := json.MarshalIndent(a.Status(), "", "  ")
		fmt.Println(string(b))
	case "run":
		a := newAgent(store)
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()
		if err := a.Run(ctx); err != nil && ctx.Err() == nil {
			fatal(err)
		}
		a.Runner.StopAll()
	default:
		usage()
	}
}

func newAgent(store *config.Store) *agent.Agent {
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))
	a := &agent.Agent{Store: store, GPU: &agent.NvidiaSMI{}, Log: log}
	docker, err := exec.LookPath("docker")
	if err != nil {
		docker = `C:\Program Files\Docker\Docker\resources\bin\docker.exe`
	}
	a.Runner = jobs.NewRunner(jobs.CLI(docker), func() jobs.Limits {
		return store.Get().Limits(a.Status().GPUInDocker)
	})
	return a
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: productify-agent pair --rental r-… --token ptok_… | live on|off | status | run")
	os.Exit(2)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}
