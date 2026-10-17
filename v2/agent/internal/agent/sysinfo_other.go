//go:build !windows

package agent

func RAMMB() int       { return 0 }
func CPUModel() string { return "" }
