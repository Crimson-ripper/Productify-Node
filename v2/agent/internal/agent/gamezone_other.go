//go:build !windows

package agent

import (
	"context"
	"runtime"
)

func CheckGamezone(context.Context) GamezoneCheck {
	return evaluateGamezone(runtime.GOOS, "", "", false, false)
}
