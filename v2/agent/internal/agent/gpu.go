package agent

import (
	"context"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"
)

// NvidiaSMI reads GPU details with nvidia-smi. With no NVIDIA driver it
// reports an empty name and no temperature.
type NvidiaSMI struct {
	once sync.Once
	name string
	vram int
}

func (g *NvidiaSMI) query(fields string) []string {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "nvidia-smi", "--query-gpu="+fields, "--format=csv,noheader,nounits")
	hideWindow(cmd)
	out, err := cmd.Output()
	if err != nil {
		return nil
	}
	line := strings.SplitN(strings.TrimSpace(string(out)), "\n", 2)[0]
	parts := strings.Split(line, ",")
	for i := range parts {
		parts[i] = strings.TrimSpace(parts[i])
	}
	return parts
}

func (g *NvidiaSMI) load() {
	g.once.Do(func() {
		if p := g.query("name,memory.total"); len(p) == 2 {
			g.name = p[0]
			g.vram, _ = strconv.Atoi(p[1])
		}
	})
}

func (g *NvidiaSMI) Name() string { g.load(); return g.name }
func (g *NvidiaSMI) VRAMMB() int  { g.load(); return g.vram }

func (g *NvidiaSMI) Temp() (int, bool) {
	p := g.query("temperature.gpu")
	if len(p) != 1 {
		return 0, false
	}
	t, err := strconv.Atoi(p[0])
	return t, err == nil
}
