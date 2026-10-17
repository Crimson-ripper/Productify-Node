//go:build windows

package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

func isService() bool {
	ok, err := svc.IsWindowsService()
	return err == nil && ok
}

type handler struct{}

func (handler) Execute(_ []string, req <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	status <- svc.Status{State: svc.StartPending}
	if err := os.MkdirAll(dirOf(logPath()), 0o700); err != nil {
		return false, 1
	}
	if fi, err := os.Stat(logPath()); err == nil && fi.Size() > 10<<20 {
		_ = os.Rename(logPath(), logPath()+".1")
	}
	logFile, err := os.OpenFile(logPath(), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return false, 1
	}
	defer logFile.Close()

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- serve(ctx, logFile) }()
	status <- svc.Status{State: svc.Running, Accepts: svc.AcceptStop | svc.AcceptShutdown}

	for {
		select {
		case c := <-req:
			switch c.Cmd {
			case svc.Interrogate:
				status <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				status <- svc.Status{State: svc.StopPending}
				cancel()
				select {
				case <-done:
				case <-time.After(60 * time.Second):
				}
				return false, 0
			}
		case err := <-done:
			cancel()
			if err != nil {
				fmt.Fprintln(logFile, "agent exited:", err)
				return false, 1 // non-zero so the recovery policy restarts us
			}
			return false, 0
		}
	}
}

func runService() {
	_ = svc.Run(serviceName, handler{})
}

func installService() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("can't reach the Windows service manager (run this from an Administrator prompt): %w", err)
	}
	defer m.Disconnect()
	if s, err := m.OpenService(serviceName); err == nil {
		s.Close()
		return fmt.Errorf("the %s service is already installed", serviceName)
	}
	s, err := m.CreateService(serviceName, exe, mgr.Config{
		DisplayName:      "Productify Node",
		Description:      "Runs Productify GPU rentals on this computer in isolated Docker containers.",
		StartType:        mgr.StartAutomatic,
		DelayedAutoStart: true, // after Docker Desktop has had a chance to start
	})
	if err != nil {
		return err
	}
	defer s.Close()
	_ = s.SetRecoveryActions([]mgr.RecoveryAction{
		{Type: mgr.ServiceRestart, Delay: 10 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 30 * time.Second},
		{Type: mgr.ServiceRestart, Delay: 2 * time.Minute},
	}, 24*60*60)
	return s.Start()
}

func uninstallService() error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("can't reach the Windows service manager (run this from an Administrator prompt): %w", err)
	}
	defer m.Disconnect()
	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("the %s service isn't installed", serviceName)
	}
	defer s.Close()
	if st, err := s.Query(); err == nil && st.State != svc.Stopped {
		_, _ = s.Control(svc.Stop)
		for i := 0; i < 60; i++ {
			if st, err := s.Query(); err != nil || st.State == svc.Stopped {
				break
			}
			time.Sleep(time.Second)
		}
	}
	return s.Delete()
}

func dirOf(p string) string {
	for i := len(p) - 1; i >= 0; i-- {
		if p[i] == '\\' || p[i] == '/' {
			return p[:i]
		}
	}
	return "."
}
