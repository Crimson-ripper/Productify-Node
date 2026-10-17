// Package config stores the node's pairing and the seller's limits.
package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"time"

	"productifynode/internal/jobs"
)

const DefaultBackend = "https://productify-backend-65tj.onrender.com"

var (
	rentalIDRe = regexp.MustCompile(`^r-[a-z0-9]{6,32}$`)
	tokenRe    = regexp.MustCompile(`^ptok_[a-f0-9]{16,64}$`)
)

// Settings is everything the agent persists.
type Settings struct {
	BackendURL   string  `json:"backend_url"`
	RentalID     string  `json:"rental_id"`
	Token        string  `json:"token"`
	NodeID       string  `json:"node_id"`
	Live         bool    `json:"live"`
	MemoryMB     int     `json:"memory_mb"`
	CPUs         float64 `json:"cpus"`
	DiskGB       int     `json:"disk_gb"`
	ShareGPU     bool    `json:"share_gpu"`
	MaxGPUTempC  int     `json:"max_gpu_temp_c"`
}

// Paired reports whether the node has a listing to serve.
func (s Settings) Paired() bool { return s.RentalID != "" && s.Token != "" }

// Limits converts the seller's settings to per-job limits.
func (s Settings) Limits(gpuInDocker bool) jobs.Limits {
	return jobs.Limits{MemoryMB: s.MemoryMB, CPUs: s.CPUs, PIDs: 512, DiskGB: s.DiskGB, ShareGPU: s.ShareGPU, GPUInDocker: gpuInDocker}
}

// Validate checks values that came from the user or the pipe.
func (s Settings) Validate() error {
	if s.RentalID != "" && !rentalIDRe.MatchString(s.RentalID) {
		return fmt.Errorf("listing id should look like r-xxxxxxxxxx")
	}
	if s.Token != "" && !tokenRe.MatchString(s.Token) {
		return fmt.Errorf("pairing token should look like ptok_ followed by 16 letters/numbers")
	}
	if !strings.HasPrefix(s.BackendURL, "https://") && !strings.HasPrefix(s.BackendURL, "http://127.0.0.1") && !strings.HasPrefix(s.BackendURL, "http://localhost") {
		return fmt.Errorf("backend must use https")
	}
	if s.MaxGPUTempC < 60 || s.MaxGPUTempC > 95 {
		return fmt.Errorf("GPU temperature limit must be between 60 and 95 °C")
	}
	return s.Limits(false).Validate()
}

func defaults() Settings {
	cpus := float64(runtime.NumCPU()) / 2
	if cpus < 1 {
		cpus = 1
	}
	return Settings{BackendURL: DefaultBackend, MemoryMB: 4096, CPUs: cpus, DiskGB: 20, MaxGPUTempC: 80}
}

// Store loads and saves Settings at a fixed path.
type Store struct {
	path     string
	restrict bool // lock the file to SYSTEM/Administrators (the real install path only)
	mu       sync.Mutex
	s        Settings
	modTime  time.Time
}

// ReloadIfChanged re-reads the file when another process (the CLI) changed it.
// Invalid contents are ignored and the current settings kept.
func (st *Store) ReloadIfChanged() (changed bool) {
	fi, err := os.Stat(st.path)
	if err != nil {
		return false
	}
	st.mu.Lock()
	defer st.mu.Unlock()
	if !fi.ModTime().After(st.modTime) {
		return false
	}
	b, err := os.ReadFile(st.path)
	if err != nil {
		return false
	}
	next := defaults()
	if json.Unmarshal(b, &next) != nil || next.Validate() != nil {
		return false
	}
	st.s, st.modTime = next, fi.ModTime()
	return true
}

// DefaultPath is %ProgramData%\ProductifyNode\node.json on Windows.
func DefaultPath() string {
	if runtime.GOOS == "windows" {
		if pd := os.Getenv("ProgramData"); pd != "" {
			return filepath.Join(pd, "ProductifyNode", "node.json")
		}
	}
	return filepath.Join("/var/lib/productify-node", "node.json")
}

func Open(path string) (*Store, error) {
	st := &Store{path: path, restrict: path == DefaultPath(), s: defaults()}
	b, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return st, nil
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(b, &st.s); err != nil {
		return nil, fmt.Errorf("settings file %s is corrupt: %w", path, err)
	}
	if fi, err := os.Stat(path); err == nil {
		st.modTime = fi.ModTime()
	}
	return st, nil
}

func (st *Store) Get() Settings {
	st.mu.Lock()
	defer st.mu.Unlock()
	return st.s
}

// Update applies fn, validates, and writes the file atomically.
func (st *Store) Update(fn func(*Settings)) (Settings, error) {
	st.mu.Lock()
	defer st.mu.Unlock()
	next := st.s
	fn(&next)
	if err := next.Validate(); err != nil {
		return st.s, err
	}
	if err := os.MkdirAll(filepath.Dir(st.path), 0o700); err != nil {
		return st.s, err
	}
	b, _ := json.MarshalIndent(next, "", "  ")
	tmp := st.path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return st.s, err
	}
	if err := os.Rename(tmp, st.path); err != nil {
		return st.s, err
	}
	if st.restrict {
		restrict(st.path)
	}
	if fi, err := os.Stat(st.path); err == nil {
		st.modTime = fi.ModTime()
	}
	st.s = next
	return next, nil
}
