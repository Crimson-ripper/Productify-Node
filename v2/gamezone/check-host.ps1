# Productify Gamezone host check (read-only: changes nothing).
# Run in PowerShell as Administrator:
#   powershell -ExecutionPolicy Bypass -File .\check-host.ps1
# Copy the whole output back to Productify.

$ErrorActionPreference = "Continue"
function Line($name, $value) { "{0,-28} {1}" -f $name, $value }

"=== Productify Gamezone host check  $(Get-Date -Format s) ==="

$cv = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"
Line "Windows" "$($cv.ProductName) | EditionID=$($cv.EditionID) | build $($cv.CurrentBuildNumber).$($cv.UBR) | $($cv.DisplayVersion)"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Line "Running as admin" $isAdmin

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Line "CPU" "$($cpu.Name.Trim()) | $($cpu.NumberOfCores) cores / $($cpu.NumberOfLogicalProcessors) threads"
Line "Virtualization in BIOS" $cpu.VirtualizationFirmwareEnabled
Line "SLAT (needed by Hyper-V)" $cpu.SecondLevelAddressTranslationExtensions
$cs = Get-CimInstance Win32_ComputerSystem
Line "RAM" ("{0:N0} GB" -f ($cs.TotalPhysicalMemory / 1GB))
Line "Hypervisor running" $cs.HypervisorPresent

if ($isAdmin) {
  $hv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -ErrorAction SilentlyContinue
  Line "Hyper-V feature" $(if ($hv) { $hv.State } else { "not available (Home edition?)" })
} else { Line "Hyper-V feature" "unknown - run this script as Administrator" }
$vmms = Get-Service vmms -ErrorAction SilentlyContinue
Line "Hyper-V service (vmms)" $(if ($vmms) { $vmms.Status } else { "not installed" })

"--- GPUs ---"
Get-CimInstance Win32_VideoController | ForEach-Object { Line "  Display adapter" "$($_.Name) | driver $($_.DriverVersion)" }
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($smi) { & nvidia-smi --query-gpu=name,memory.total,driver_version,encoder.stats.sessionCount --format=csv,noheader 2>$null | ForEach-Object { Line "  nvidia-smi" $_ } }
else { Line "  nvidia-smi" "not found" }

"--- GPU partitioning (GPU-P) ---"
$cmd = Get-Command Get-VMHostPartitionableGpu, Get-VMPartitionableGpu -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $cmd) { Line "Partitionable GPUs" "Hyper-V PowerShell module not installed yet" }
else {
  $gpus = @(& $cmd.Name -ErrorAction SilentlyContinue)
  Line "Partitionable GPUs" $gpus.Count
  foreach ($g in $gpus) { Line "  GPU" "$($g.Name) | partitions $($g.ValidPartitionCounts -join ',')" }
}

"--- Disk ---"
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null } | ForEach-Object { Line "  Drive $($_.Name):" ("{0:N0} GB free" -f ($_.Free / 1GB)) }
"=== end ==="
