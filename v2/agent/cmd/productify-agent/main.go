// productify-agent runs on a seller's machine and serves their Productify GPU listing.
//
// Service (needs an elevated prompt):
//
//	productify-agent install      install and start the Windows service
//	productify-agent uninstall    stop and remove it (running jobs are removed)
//
// Control the running agent (talks to it over its named pipe):
//
//	productify-agent status
//	productify-agent pair --rental r-xxxxxxxxxx --token ptok_xxxxxxxxxxxxxxxx
//	productify-agent live on|off
//	productify-agent limits [--memory-mb N] [--cpus N] [--disk-gb N] [--share-gpu=true|false] [--max-temp N]
//	productify-agent stop         emergency stop: remove every job and pause
//	productify-agent logs
//
// Development:
//
//	productify-agent run          run in the foreground instead of as a service
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"

	"productifynode/internal/agent"
	"productifynode/internal/config"
	"productifynode/internal/ipc"
	"productifynode/internal/jobs"
)

const serviceName = "ProductifyNode"

func main() {
	if isService() {
		runService()
		return
	}
	if len(os.Args) < 2 {
		usage()
	}
	switch cmd := os.Args[1]; cmd {
	case "run":
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()
		if err := serve(ctx, os.Stderr); err != nil {
			fatal(err)
		}
	case "install":
		check(installService())
		fmt.Println("Installed and started. Pair it with: productify-agent pair --rental … --token …")
	case "uninstall":
		check(uninstallService())
		fmt.Println("Removed.")
	case "status":
		show(control(ipc.Request{Op: "status"}))
	case "pair":
		fs := flag.NewFlagSet("pair", flag.ExitOnError)
		rental := fs.String("rental", "", "listing id from Seller studio (r-…)")
		token := fs.String("token", "", "pairing token from Seller studio (ptok_…)")
		_ = fs.Parse(os.Args[2:])
		show(control(ipc.Request{Op: "pair", RentalID: *rental, Token: *token}))
		fmt.Println("Paired. Renting stays off until you run: productify-agent live on")
	case "live":
		if len(os.Args) < 3 || (os.Args[2] != "on" && os.Args[2] != "off") {
			usage()
		}
		on := os.Args[2] == "on"
		show(control(ipc.Request{Op: "live", Live: &on}))
	case "limits":
		fs := flag.NewFlagSet("limits", flag.ExitOnError)
		req := ipc.Request{Op: "limits"}
		mem, cpus, disk, temp := fs.Int("memory-mb", 0, ""), fs.Float64("cpus", 0, ""), fs.Int("disk-gb", 0, ""), fs.Int("max-temp", 0, "")
		gpu := fs.String("share-gpu", "", "true or false")
		_ = fs.Parse(os.Args[2:])
		if *mem > 0 {
			req.MemoryMB = mem
		}
		if *cpus > 0 {
			req.CPUs = cpus
		}
		if *disk > 0 {
			req.DiskGB = disk
		}
		if *temp > 0 {
			req.MaxTempC = temp
		}
		if *gpu != "" {
			b := *gpu == "true"
			req.ShareGPU = &b
		}
		show(control(req))
	case "stop":
		show(control(ipc.Request{Op: "emergency_stop"}))
	case "logs":
		show(control(ipc.Request{Op: "logs"}))
	default:
		usage()
	}
}

// serve runs the agent and its control pipe until ctx ends.
func serve(ctx context.Context, logOut io.Writer) error {
	store, err := config.Open(configPath())
	if err != nil {
		return err
	}
	buf := agent.NewLogBuffer(slog.NewTextHandler(logOut, nil), 500)
	a := &agent.Agent{Store: store, GPU: &agent.NvidiaSMI{}, Log: slog.New(buf), Logs: buf}
	a.Runner = jobs.NewRunner(jobs.CLI(dockerPath()), func() jobs.Limits {
		return store.Get().Limits(a.Status().GPUInDocker)
	})

	l, err := ipc.Listen(ipc.PipeName)
	if err != nil {
		return fmt.Errorf("control pipe: %w (is another agent already running?)", err)
	}
	go func() {
		if err := ipc.Serve(ctx, l, a.Control); err != nil {
			a.Log.Error("control pipe stopped", "err", err)
		}
	}()
	a.Log.Info("agent started", "version", agent.Version)
	err = a.Run(ctx)
	n := a.Runner.StopAll() // never leave renter containers behind when the agent exits
	a.Log.Info("agent stopped", "jobs_removed", n)
	if ctx.Err() != nil {
		return nil
	}
	return err
}

func configPath() string {
	if p := os.Getenv("PRODUCTIFY_NODE_CONFIG"); p != "" {
		return p
	}
	return config.DefaultPath()
}

func logPath() string { return filepath.Join(filepath.Dir(configPath()), "agent.log") }

func dockerPath() string {
	if p := os.Getenv("PRODUCTIFY_DOCKER"); p != "" { // integration tests point this at a stand-in
		return p
	}
	if p, err := exec.LookPath("docker"); err == nil {
		return p
	}
	return `C:\Program Files\Docker\Docker\resources\bin\docker.exe`
}

func control(req ipc.Request) json.RawMessage {
	c, err := ipc.Dial(ipc.PipeName)
	if err != nil {
		fatal(fmt.Errorf("the Productify Node service isn't running (%v). Install it with: productify-agent install", err))
	}
	data, err := ipc.Call(c, req)
	check(err)
	return data
}

func show(data json.RawMessage) {
	var v any
	_ = json.Unmarshal(data, &v)
	b, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(b))
}

func check(err error) {
	if err != nil {
		fatal(err)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: productify-agent install | uninstall | status | pair --rental r-… --token ptok_… | live on|off | limits … | stop | logs | run")
	os.Exit(2)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}
