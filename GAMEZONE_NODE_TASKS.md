# Productify Node + PG Connect for Gamezone — task list (resume file)

**How to resume after any interruption:** open this file, find the first task that is not `[x]`,
read its "Notes / state" line, and continue from there. Update the checkbox and notes after every step.
Rule from the user: **ask before doing anything new**; each phase below is approved when the user says go.

Status keys: `[ ]` not started · `[~]` in progress · `[x]` done · `[?]` waiting for the user

## Goal (user, 2026-10-24)
A renter picks a Productify Node machine on the site, gets a code, opens PG Connect, and plays a
game from **their own Steam account**. Test machine: Suryansh's RTX 4060 laptop.

## Decisions (2026-10-24)
- **Gamezone hosting only on Windows Pro / Enterprise / Education** (they have Hyper-V). Windows Home
  hosts stay on JupyterLab-type container work only.
- Renter runs in a **separate Hyper-V Windows VM** with a GPU partition (GPU-P), never on the owner's
  desktop. VM is reset after each session.
- Games whose anti-cheat blocks VMs (Valorant, some Battlefield / Call of Duty titles) are listed
  as "not supported".
- `v2/go-agent` gets merged into `main` as part of this work.
- Gamezone website work (`gamezone-library` branch, GAMEZONE_TASKS.md) is paused meanwhile.

## Open risks (tracked, not blocking the pilot)
- Windows licence for renter VMs: renting Windows desktops needs a provider licence (SPLA) before going public.
- NVIDIA GeForce driver licence ("commercial hosting services") — legal review before going public.
- GPU-P on GeForce is unofficial on client Windows; driver updates can break it.

## Phase 0 — Setup
- [x] 0.1 Merge `v2/go-agent` into `main` (fast-forward, 9 commits). Notes: done 2026-10-24; work continues on main.
- [x] 0.2 Confirm Suryansh's laptop is Windows Pro (Home needs an upgrade before Gamezone tests). Notes: user confirmed Pro (2026-10-24). Next: Suryansh runs v2/gamezone/check-host.ps1, turns on Hyper-V, sends output.

## Phase 1 — Eligibility
- [x] 1.1 Agent reports Windows edition, Hyper-V state, GPU-P support (`Get-VMHostPartitionableGpu`). Notes: internal/agent/gamezone*.go; sent as "gamezone" in hello + Status; rechecked every 10 min. Verified on this PC (Win 10 Home → not eligible, 3 reasons).
- [~] 1.2 Backend stores `gamezone_eligible` + reasons; only eligible machines can take game sessions. Notes: backend stores rentals.gamezone (live on main b65eec7). Enforcement comes with game sessions in 4.1.
- [x] 1.3 Host app shows eligibility and why not (e.g. "Windows Home — Gamezone needs Pro"). Notes: Gamezone line + reasons in the app status panel. Not yet in a released build.

## Phase 2 — Gaming VM on the host
- [~] 2.1 Agent builds a base Windows VM (Hyper-V, Gen 2, GPU partition, driver files copied from host). Notes: v2/gamezone/gamezone-vm.ps1 drafted (PrepareBase/Start/Stop), UNTESTED; needs a base image made by hand (Win 11 Enterprise eval ISO). Agent wiring after the laptop test.
- [~] 2.2 Per-session VM from a differencing disk / checkpoint; destroyed or reset after the session. Notes: Start uses a differencing disk, Stop deletes VM + disk. Untested.
- [ ] 2.3 VM network isolated from the owner's LAN (same rules as the v2.1 egress proxy where possible). Notes: —

## Phase 3 — Streaming inside the VM
- [ ] 3.1 Sunshine + virtual display driver installed in the base image; NVENC confirmed. Notes: —
- [ ] 3.2 Steam client in the base image (renter signs in with their own account; nothing stored after reset). Notes: —
- [ ] 3.3 Reach the VM from PG Connect (direct UDP if possible, else the WireGuard path PG Connect already has). Notes: —

## Phase 4 — Backend + site
- [ ] 4.1 Backend: start a game session on a Node machine → agent starts VM → session code for PG Connect. Notes: —
- [ ] 4.2 Billing/metering for game sessions (same credit rules as instances; idle pause later). Notes: —
- [ ] 4.3 Site: "Play on this machine" for eligible machines → code + PG Connect download. Notes: —

## Phase 5 — End-to-end test
- [ ] 5.1 On Suryansh's laptop: pick machine → code → PG Connect → Steam sign-in → play a free game. Notes: —
- [ ] 5.2 Check: VM reset after session, owner's files/LAN unreachable, billing stops on end. Notes: —
- [ ] 5.3 Report results to the user. Notes: —
