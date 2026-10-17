// Package ids validates identifiers that arrive from the backend before they
// are used in container names, volume names or anything else on the host.
package ids

import (
	"fmt"
	"regexp"
)

var jobID = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,62}$`)

// ValidJobID reports whether id is safe to use as part of a Docker object name.
// It rules out path separators, dots and anything that could escape a prefix.
func ValidJobID(id string) error {
	if !jobID.MatchString(id) {
		return fmt.Errorf("invalid job id %q", id)
	}
	return nil
}
