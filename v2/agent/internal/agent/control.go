package agent

import (
	"fmt"
	"strings"

	"productifynode/internal/config"
	"productifynode/internal/ipc"
)

// Control answers requests from the desktop app / CLI over the named pipe.
func (a *Agent) Control(req ipc.Request) (any, error) {
	switch req.Op {
	case "status":
		return map[string]any{"status": a.Status(), "settings": redact(a.Store.Get()), "version": Version}, nil

	case "pair":
		rental, token := strings.TrimSpace(req.RentalID), strings.TrimSpace(req.Token)
		if code := strings.TrimSpace(req.Code); code != "" {
			// Pairing code from Seller studio: "<listing id>.<token>"
			var ok bool
			if rental, token, ok = strings.Cut(code, "."); !ok {
				return nil, fmt.Errorf("that doesn't look like a pairing code — copy it again from Seller studio")
			}
		}
		if rental == "" || token == "" {
			return nil, fmt.Errorf("paste the pairing code from Seller studio")
		}
		// A new pairing starts paused, so the seller decides when renters can connect.
		_, err := a.Store.Update(func(s *config.Settings) { s.RentalID, s.Token, s.Live = rental, token, false })
		if err != nil {
			return nil, err
		}
		a.Log.Info("paired", "rental", rental)
		return a.Status(), nil

	case "live":
		if req.Live == nil {
			return nil, fmt.Errorf("say whether to go live or pause")
		}
		if *req.Live && !a.Store.Get().Paired() {
			return nil, fmt.Errorf("pair this computer with a listing first")
		}
		if err := a.SetLive(*req.Live); err != nil {
			return nil, err
		}
		return a.Status(), nil

	case "limits":
		_, err := a.Store.Update(func(s *config.Settings) {
			if req.MemoryMB != nil {
				s.MemoryMB = *req.MemoryMB
			}
			if req.CPUs != nil {
				s.CPUs = *req.CPUs
			}
			if req.DiskGB != nil {
				s.DiskGB = *req.DiskGB
			}
			if req.ShareGPU != nil {
				s.ShareGPU = *req.ShareGPU
			}
			if req.MaxTempC != nil {
				s.MaxGPUTempC = *req.MaxTempC
			}
		})
		if err != nil {
			return nil, err
		}
		return redact(a.Store.Get()), nil

	case "emergency_stop":
		return map[string]int{"jobs_stopped": a.EmergencyStop()}, nil

	case "logs":
		if a.Logs == nil {
			return []LogLine{}, nil
		}
		return a.Logs.Lines(), nil
	}
	return nil, fmt.Errorf("unknown request %q", req.Op)
}

// redact hides the pairing token: the app shows whether one is set, never the value.
func redact(s config.Settings) config.Settings {
	if s.Token != "" {
		s.Token = s.Token[:5] + "…" // "ptok_…"
	}
	return s
}
