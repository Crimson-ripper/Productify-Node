# Productify Gamezone: per-session Windows VM with a GPU partition (Hyper-V GPU-P).
# Pilot script, run as Administrator on a Windows Pro/Enterprise/Education host with Hyper-V on.
# STATUS: untested; first run is on Suryansh's laptop (GAMEZONE_NODE_TASKS.md, Phase 2).
#
#   .\gamezone-vm.ps1 -Action PrepareBase -BaseVhd D:\Gamezone\base.vhdx
#       Copies the host's NVIDIA driver files into the base image (redo after every driver update).
#   .\gamezone-vm.ps1 -Action Start -BaseVhd D:\Gamezone\base.vhdx -Session abc123
#       New VM "pfy-gz-abc123" on a throwaway differencing disk, with a GPU partition, started.
#   .\gamezone-vm.ps1 -Action Stop -Session abc123
#       Turns the VM off and deletes it and its disk, so nothing the renter did survives.
#   .\gamezone-vm.ps1 -Action List
#
# The base image is a normal Windows install made once by hand in Hyper-V (pilot: Windows 11
# Enterprise evaluation ISO), with Steam, Sunshine and a virtual display driver installed
# (Phase 3), then shut down. Session VMs never write to it.

param(
  [Parameter(Mandatory)][ValidateSet("PrepareBase", "Start", "Stop", "List")] [string]$Action,
  [string]$BaseVhd = "",
  [ValidatePattern('^[A-Za-z0-9-]{1,40}$')] [string]$Session = "",
  [string]$WorkDir = "$env:ProgramData\Productify\Gamezone",
  [int]$Cpus = 4,
  [int64]$MemoryGB = 8,
  [ValidateRange(10, 100)] [int]$GpuPercent = 100,
  [string]$Switch = "Default Switch"
)

$ErrorActionPreference = "Stop"
$Prefix = "pfy-gz-"

function Assert-Ready {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  if (-not ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run as Administrator." }
  if (-not (Get-Command New-VM -ErrorAction SilentlyContinue)) { throw "Hyper-V isn't installed." }
}

function Get-PartitionableGpu {
  $c = Get-Command Get-VMHostPartitionableGpu, Get-VMPartitionableGpu -ErrorAction SilentlyContinue | Select-Object -First 1
  $g = if ($c) { @(& $c.Name) } else { @() }
  if ($g.Count -eq 0) { throw "No GPU that Hyper-V can partition." }
  return $g[0]
}

# Copy the host's NVIDIA user-mode driver into the guest, where GPU-P expects it
# (guest \Windows\System32\HostDriverStore). This is the step Easy-GPU-PV automates.
function Copy-HostDriver([string]$vhd) {
  $mounted = Mount-VHD -Path $vhd -PassThru | Get-Disk | Get-Partition | Get-Volume |
    Where-Object { $_.DriveLetter -and (Test-Path "$($_.DriveLetter):\Windows\System32") } | Select-Object -First 1
  if (-not $mounted) { Dismount-VHD $vhd; throw "No Windows install found inside $vhd." }
  $guest = "$($mounted.DriveLetter):"
  try {
    $nv = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match "NVIDIA" } | Select-Object -First 1
    if (-not $nv) { throw "No NVIDIA GPU on the host." }
    $inf = (Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName -eq $nv.Name } | Select-Object -First 1).InfName
    $repo = Get-ChildItem "$env:SystemRoot\System32\DriverStore\FileRepository" -Directory |
      Where-Object { Test-Path (Join-Path $_.FullName $inf) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $repo) { throw "Couldn't find the NVIDIA driver folder for $inf." }
    $dest = "$guest\Windows\System32\HostDriverStore\FileRepository"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Get-ChildItem $dest -Directory -Filter "nv*" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
    Copy-Item $repo.FullName $dest -Recurse -Force
    Copy-Item "$env:SystemRoot\System32\nv*.dll", "$env:SystemRoot\System32\nvidia-smi.exe" "$guest\Windows\System32\" -Force -ErrorAction SilentlyContinue
    "Copied driver $($repo.Name) into the base image."
  } finally { Dismount-VHD $vhd }
}

# Keep the renter off the owner's home network: deny all private/link-local addresses on the VM's
# switch port, except DNS to the Hyper-V gateway (needed for internet). These ACLs live on the host's
# virtual switch, so an admin inside the VM can't remove them. Same idea as the v2.1 egress proxy.
$PrivateRanges = "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10"

function Protect-HomeNetwork([string]$vmName) {
  $hostIf = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.InterfaceAlias -eq "vEthernet ($Switch)" } | Select-Object -First 1
  if (-not $hostIf) { throw "Can't find the host side of switch '$Switch'." }
  $gw = $hostIf.IPAddress
  $w = 10
  foreach ($r in $PrivateRanges) {
    foreach ($dir in "Outbound", "Inbound") {
      Add-VMNetworkAdapterExtendedAcl -VMName $vmName -Action Deny -Direction $dir -RemoteIPAddress $r -Weight $w
      $w++
    }
  }
  foreach ($proto in "UDP", "TCP") {  # higher weight wins: DNS to the gateway only
    Add-VMNetworkAdapterExtendedAcl -VMName $vmName -Action Allow -Direction Outbound -RemoteIPAddress "$gw/32" `
      -Protocol $proto -RemotePort 53 -Stateful $true -Weight (100 + [int]($proto -eq "TCP"))
  }
  # DHCP with the gateway (lease renewals are unicast to it; replies come from its port 67).
  Add-VMNetworkAdapterExtendedAcl -VMName $vmName -Action Allow -Direction Outbound -RemoteIPAddress "$gw/32" -Protocol UDP -RemotePort 67 -Weight 102
  Add-VMNetworkAdapterExtendedAcl -VMName $vmName -Action Allow -Direction Inbound -RemoteIPAddress "$gw/32" -Protocol UDP -RemotePort 67 -LocalPort 68 -Weight 103
  # Block IPv6 to the LAN too (link-local and unique-local); public IPv6 stays allowed.
  foreach ($r in "fe80::/10", "fc00::/7") {
    Add-VMNetworkAdapterExtendedAcl -VMName $vmName -Action Deny -Direction Outbound -RemoteIPAddress $r -Weight $w; $w++
  }
  Set-VMNetworkAdapter -VMName $vmName -DhcpGuard On -RouterGuard On -MacAddressSpoofing Off
}

function Start-Session {
  if (-not $Session) { throw "-Session is required." }
  if (-not (Test-Path $BaseVhd)) { throw "Base image not found: $BaseVhd" }
  $name = "$Prefix$Session"
  if (Get-VM -Name $name -ErrorAction SilentlyContinue) { throw "$name already exists." }
  $gpu = Get-PartitionableGpu
  New-Item -ItemType Directory -Force $WorkDir | Out-Null
  $disk = Join-Path $WorkDir "$name.vhdx"
  New-VHD -Path $disk -ParentPath $BaseVhd -Differencing | Out-Null   # renter changes land here only

  $vm = New-VM -Name $name -Generation 2 -MemoryStartupBytes ($MemoryGB * 1GB) -VHDPath $disk -SwitchName $Switch -Path $WorkDir
  Set-VM $vm -ProcessorCount $Cpus -StaticMemory -AutomaticCheckpointsEnabled $false -CheckpointType Disabled `
    -AutomaticStopAction TurnOff -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1GB -HighMemoryMappedIoSpace 32GB
  Set-VMFirmware $vm -EnableSecureBoot On
  Set-VMKeyProtector $vm -NewLocalKeyProtector; Enable-VMTPM $vm   # Windows 11 needs a TPM

  Add-VMGpuPartitionAdapter -VMName $name
  # Share of each GPU resource, from GPU-P's maximums (100% = the whole card).
  $f = $GpuPercent / 100
  $max = @{ VRAM = 1000000000; Encode = [uint64]::MaxValue / 2; Decode = 1000000000; Compute = 1000000000 }
  Set-VMGpuPartitionAdapter -VMName $name `
    -MinPartitionVRAM 1 -MaxPartitionVRAM ([uint64]($max.VRAM * $f)) -OptimalPartitionVRAM ([uint64]($max.VRAM * $f)) `
    -MinPartitionEncode 1 -MaxPartitionEncode ([uint64]($max.Encode * $f)) -OptimalPartitionEncode ([uint64]($max.Encode * $f)) `
    -MinPartitionDecode 1 -MaxPartitionDecode ([uint64]($max.Decode * $f)) -OptimalPartitionDecode ([uint64]($max.Decode * $f)) `
    -MinPartitionCompute 1 -MaxPartitionCompute ([uint64]($max.Compute * $f)) -OptimalPartitionCompute ([uint64]($max.Compute * $f))

  Protect-HomeNetwork $name

  Start-VM $vm
  [pscustomobject]@{ vm = $name; gpu = $gpu.Name; cpus = $Cpus; memory_gb = $MemoryGB; disk = $disk } | ConvertTo-Json -Compress
}

function Stop-Session {
  if (-not $Session) { throw "-Session is required." }
  $name = "$Prefix$Session"
  $vm = Get-VM -Name $name -ErrorAction SilentlyContinue
  if ($vm) {
    Stop-VM $vm -TurnOff -Force -ErrorAction SilentlyContinue
    $disks = (Get-VMHardDiskDrive $vm).Path
    Remove-VM $vm -Force
    foreach ($d in $disks) { if ($d -and $d -ne $BaseVhd -and (Split-Path $d -Leaf) -like "$Prefix*") { Remove-Item $d -Force -ErrorAction SilentlyContinue } }
  }
  Remove-Item (Join-Path $WorkDir $name) -Recurse -Force -ErrorAction SilentlyContinue
  "stopped $name"
}

Assert-Ready
switch ($Action) {
  "PrepareBase" { if (-not (Test-Path $BaseVhd)) { throw "Base image not found: $BaseVhd" }; Copy-HostDriver $BaseVhd }
  "Start" { Start-Session }
  "Stop" { Stop-Session }
  "List" { Get-VM -Name "$Prefix*" | Select-Object Name, State, Uptime, CPUUsage, MemoryAssigned | Format-Table -AutoSize }
}
