// Package templates is the allowlist of container images a renter can run.
// The backend only ever names a template; the image reference (pinned by
// digest) lives here, so a compromised backend cannot run arbitrary images.
package templates

import "fmt"

type Template struct {
	Name  string
	Image string // repository@sha256:… — never a mutable tag on its own
	GPU   bool   // needs GPU passthrough to be useful
}

var allowed = map[string]Template{
	"python": {
		Name:  "python",
		Image: "python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1",
	},
	"pytorch": {
		Name:  "pytorch",
		Image: "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime@sha256:393fa73fbcfd290b46483cebc29a284fcc10d5be493e3d4844f9781152c2daa4",
		GPU:   true,
	},
}

// Lookup returns the template with the given name, or an error if it isn't allowed.
func Lookup(name string) (Template, error) {
	t, ok := allowed[name]
	if !ok {
		return Template{}, fmt.Errorf("template %q is not allowed", name)
	}
	return t, nil
}
