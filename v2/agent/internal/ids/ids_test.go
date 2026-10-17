package ids

import "testing"

func TestValidJobID(t *testing.T) {
	good := []string{"a", "job-1", "inst-3f9a2c", "0abc"}
	bad := []string{"", "-lead", "UPPER", "../etc", "a/b", `a\b`, "a.b", "a b", "x;rm", string(make([]byte, 70))}
	for _, id := range good {
		if err := ValidJobID(id); err != nil {
			t.Errorf("%q should be valid: %v", id, err)
		}
	}
	for _, id := range bad {
		if ValidJobID(id) == nil {
			t.Errorf("%q should be rejected", id)
		}
	}
}
