package agent

import "strings"

// GamezoneCheck says whether this machine may host Gamezone sessions. Gamezone runs each renter
// in a separate Hyper-V VM with a slice of the GPU, so it needs Windows Pro, Enterprise or
// Education (Home has no Hyper-V), the Hyper-V service running, and a GPU Hyper-V can partition.
// Machines that fail stay available for container work (JupyterLab and similar).
type GamezoneCheck struct {
	Eligible     bool     `json:"eligible"`
	Edition      string   `json:"edition"`       // e.g. "Windows 11 Pro"
	EditionID    string   `json:"edition_id"`    // registry EditionID, e.g. "Professional"
	HyperV       bool     `json:"hyperv"`        // Hyper-V Virtual Machine Management service running
	GPUPartition bool     `json:"gpu_partition"` // Get-VMHostPartitionableGpu lists a GPU
	Reasons      []string `json:"reasons"`       // why not eligible, in words for the host app
}

// gamezoneEditions are EditionIDs that include Hyper-V. Home is "Core" / "CoreSingleLanguage" /
// "CoreCountrySpecific"; Server editions are left out of the pilot.
var gamezoneEditions = []string{"Professional", "ProfessionalWorkstation", "ProfessionalEducation",
	"Enterprise", "EnterpriseS", "Education"}

func editionAllowsGamezone(id string) bool {
	for _, e := range gamezoneEditions {
		if strings.EqualFold(id, e) || strings.EqualFold(id, e+"N") {
			return true
		}
	}
	return false
}

// evaluateGamezone turns the raw facts into a decision with reasons.
func evaluateGamezone(goos, editionName, editionID string, hyperV, gpuPartition bool) GamezoneCheck {
	c := GamezoneCheck{Edition: editionName, EditionID: editionID, HyperV: hyperV, GPUPartition: gpuPartition}
	if goos != "windows" {
		c.Reasons = append(c.Reasons, "Gamezone hosting needs Windows 10/11 Pro, Enterprise or Education.")
		return c
	}
	if !editionAllowsGamezone(editionID) {
		name := editionName
		if name == "" {
			name = "This Windows edition"
		}
		c.Reasons = append(c.Reasons, name+" can't host Gamezone: it needs Windows Pro, Enterprise or Education (for Hyper-V). It can still run JupyterLab and other container work.")
	}
	if !hyperV {
		c.Reasons = append(c.Reasons, "Hyper-V isn't turned on. Turn on \"Hyper-V\" in Windows Features and restart.")
	}
	if !gpuPartition {
		c.Reasons = append(c.Reasons, "Hyper-V can't share this GPU with a virtual machine (no partitionable GPU found). Update the NVIDIA driver and check again.")
	}
	c.Eligible = len(c.Reasons) == 0
	return c
}
