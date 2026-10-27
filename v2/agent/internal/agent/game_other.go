//go:build !windows

package agent

func newGameVMs(string) *GameVMs { return nil }
