//go:build !windows

package main

import "errors"

func isService() bool { return false }
func runService()     {}

// On Linux, run `productify-agent run` under systemd instead.
func installService() error   { return errors.New("install is Windows-only; use a systemd unit running `productify-agent run`") }
func uninstallService() error { return errors.New("uninstall is Windows-only") }
