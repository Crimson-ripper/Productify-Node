package config

import (
	"path/filepath"
	"testing"
)

func TestUpdateValidatesAndPersists(t *testing.T) {
	path := filepath.Join(t.TempDir(), "node.json")
	st, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if st.Get().Paired() {
		t.Fatal("fresh store should not be paired")
	}
	if _, err := st.Update(func(s *Settings) { s.Token = "not-a-token" }); err == nil {
		t.Error("bad token accepted")
	}
	if _, err := st.Update(func(s *Settings) { s.BackendURL = "http://evil.example" }); err == nil {
		t.Error("plain http backend accepted")
	}
	if _, err := st.Update(func(s *Settings) { s.MaxGPUTempC = 120 }); err == nil {
		t.Error("unsafe temperature accepted")
	}
	if _, err := st.Update(func(s *Settings) { s.RentalID = "r-abc123def4"; s.Token = "ptok_0123456789abcdef" }); err != nil {
		t.Fatal(err)
	}
	again, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if !again.Get().Paired() || again.Get().RentalID != "r-abc123def4" {
		t.Errorf("not persisted: %+v", again.Get())
	}
}
