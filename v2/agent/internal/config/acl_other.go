//go:build !windows

package config

func restrict(string) {} // file is already written 0600
