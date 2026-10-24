package agent

import (
	"strings"
	"testing"
)

func TestGamezoneEligibility(t *testing.T) {
	cases := []struct {
		name, goos, edition, id string
		hv, gpup, want          bool
		reason                  string
	}{
		{"pro ready", "windows", "Windows 11 Pro", "Professional", true, true, true, ""},
		{"enterprise ready", "windows", "Windows 10 Enterprise", "Enterprise", true, true, true, ""},
		{"education N ready", "windows", "Windows 11 Education N", "EducationN", true, true, true, ""},
		{"home", "windows", "Windows 11 Home Single Language", "CoreSingleLanguage", false, false, false, "needs Windows Pro"},
		{"pro without hyper-v", "windows", "Windows 11 Pro", "Professional", false, false, false, "Hyper-V isn't turned on"},
		{"pro, gpu not partitionable", "windows", "Windows 11 Pro", "Professional", true, false, false, "can't share this GPU"},
		{"linux", "linux", "", "", false, false, false, "needs Windows"},
	}
	for _, c := range cases {
		got := evaluateGamezone(c.goos, c.edition, c.id, c.hv, c.gpup)
		if got.Eligible != c.want {
			t.Errorf("%s: eligible=%v, want %v (%v)", c.name, got.Eligible, c.want, got.Reasons)
		}
		if c.reason != "" && !strings.Contains(strings.Join(got.Reasons, " "), c.reason) {
			t.Errorf("%s: reasons %q missing %q", c.name, got.Reasons, c.reason)
		}
		if c.want && len(got.Reasons) != 0 {
			t.Errorf("%s: eligible but has reasons %q", c.name, got.Reasons)
		}
	}
}

func TestHomeStillGetsAllReasons(t *testing.T) {
	got := evaluateGamezone("windows", "Windows 10 Home", "Core", false, false)
	if len(got.Reasons) != 3 {
		t.Fatalf("want 3 reasons for a bare Home machine, got %q", got.Reasons)
	}
}
