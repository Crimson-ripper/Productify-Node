package agent

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// LogLine is one entry shown in the desktop app's log view.
type LogLine struct {
	Time    time.Time         `json:"time"`
	Level   string            `json:"level"`
	Message string            `json:"message"`
	Attrs   map[string]string `json:"attrs,omitempty"`
}

// LogBuffer is a slog.Handler that keeps the last N lines in memory and also
// forwards to another handler (the log file / event log).
type LogBuffer struct {
	next  slog.Handler
	mu    *sync.Mutex
	lines *[]LogLine
	max   int
	attrs []slog.Attr
}

func NewLogBuffer(next slog.Handler, max int) *LogBuffer {
	lines := make([]LogLine, 0, max)
	return &LogBuffer{next: next, mu: &sync.Mutex{}, lines: &lines, max: max}
}

func (b *LogBuffer) Enabled(ctx context.Context, l slog.Level) bool { return b.next.Enabled(ctx, l) }

func (b *LogBuffer) Handle(ctx context.Context, r slog.Record) error {
	line := LogLine{Time: r.Time, Level: r.Level.String(), Message: r.Message, Attrs: map[string]string{}}
	for _, a := range b.attrs {
		line.Attrs[a.Key] = a.Value.String()
	}
	r.Attrs(func(a slog.Attr) bool {
		line.Attrs[a.Key] = a.Value.String()
		return true
	})
	b.mu.Lock()
	if len(*b.lines) == b.max {
		*b.lines = append((*b.lines)[:0], (*b.lines)[1:]...)
	}
	*b.lines = append(*b.lines, line)
	b.mu.Unlock()
	return b.next.Handle(ctx, r)
}

func (b *LogBuffer) WithAttrs(attrs []slog.Attr) slog.Handler {
	c := *b
	c.next = b.next.WithAttrs(attrs)
	c.attrs = append(append([]slog.Attr{}, b.attrs...), attrs...)
	return &c
}

func (b *LogBuffer) WithGroup(name string) slog.Handler {
	c := *b
	c.next = b.next.WithGroup(name)
	return &c
}

// Lines returns a copy, oldest first.
func (b *LogBuffer) Lines() []LogLine {
	b.mu.Lock()
	defer b.mu.Unlock()
	return append([]LogLine(nil), *b.lines...)
}
