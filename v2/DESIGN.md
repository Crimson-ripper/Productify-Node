# Productify Node v2 — design

Productify Node lets a seller rent out their computer's GPU on productifynow.com.
Renters run containerised workloads on the seller's machine. The seller must be
able to trust that a renter can never reach their files, accounts, screen,
home network, or the computer itself.

v1 (the Python app in the repo root) is retired. It ran renter code directly on
the host when Docker was missing, exposed an unauthenticated local HTTP API to
every website, and streamed the seller's real desktop for Gamezone.

## Scope of v2.0

In: GPU/CPU compute rental in Docker containers, pairing with a listing,
pause/resume, emergency stop, resource limits, thermal guard, live status,
signed installer and updates.

Out (until a per-session VM design exists): Gamezone game hosting, Sunshine,
Moonlight, input injection, UPnP, opening firewall ports.

## Components

```
            productifynow backend (FastAPI)
                    ^
                    | WSS /ws/node/v1   (outbound only, token auth)
                    |
  +-----------------+-------------------------------+
  | productify-agent  (Go, Windows service)         |
  |   - tunnel: one WebSocket, reconnect w/ backoff |
  |   - jobs:   Docker Engine API, hardened only    |
  |   - guard:  thermal, RAM/CPU/disk limits        |
  |   - ipc:    named pipe for the desktop app      |
  +-----------------+-------------------------------+
                    | \\.\pipe\productify-node (ACL: this user + admins)
  +-----------------+-------------------------------+
  | Productify Node app (Tauri)                     |
  |   pair, go live / pause, limits, status, logs   |
  +-------------------------------------------------+
```

* The agent opens **no listening network ports**. The desktop app talks to it
  over a named pipe whose ACL allows only the signed-in user and
  Administrators, so a website in the browser cannot reach it.
* The agent never runs renter code outside a container. If Docker is not
  available the node reports `ready=false` and refuses jobs.

## Pairing

1. Seller creates a GPU listing; the backend issues `pairing_token` (`ptok_…`).
2. Seller pastes the token into the app (or clicks a `productify://pair?…`
   link, which only pre-fills the field — the seller still confirms).
3. Agent stores `{rental_id, token}` in `%ProgramData%\ProductifyNode\node.json`,
   readable only by SYSTEM and Administrators.
4. Every tunnel connection sends `Authorization: Bearer <token>`; the backend
   checks it against the rental with a constant-time compare.

## Tunnel protocol (`/ws/node/v1`)

All frames are JSON: `{"type": "...", "id": "<uuid>", ...}`. Replies carry the
request's `id` in `re`.

Agent -> backend

| type        | when                       | fields |
|-------------|----------------------------|--------|
| `hello`     | after connect              | `agent_version`, `node_id`, `os`, `gpu`, `vram_mb`, `cpu_cores`, `ram_mb`, `docker` (bool), `gpu_in_docker` (bool), `live` (bool) |
| `heartbeat` | every 15 s                 | `live`, `jobs` (count), `gpu_temp_c`, `paused_reason` |
| `result`    | reply to a request         | `re`, `ok`, `error?`, plus per-request fields |
| `event`     | job ended / was killed     | `job_id`, `kind` (`exited`, `killed_thermal`, `killed_quota`, `stopped`), `exit_code?` |

Backend -> agent

| type        | fields | agent reply |
|-------------|--------|-------------|
| `job.start` | `job_id`, `template` | `result` with `container` |
| `job.exec`  | `job_id`, `argv` (list) or `python` (string), `timeout_s` (≤ 120) | `result` with `stdout`, `stderr`, `exit_code` (each stream ≤ 256 KiB) |
| `job.stop`  | `job_id` | `result` |
| `ping`      | — | `result` |

Unknown types get `{"ok": false, "error": "unsupported"}`.

## Container rules (non-negotiable)

* **Images**: only templates from the agent's built-in allowlist, pinned by
  digest. The backend sends a template name, never an image string.
* **IDs**: `job_id` must match `^[a-z0-9][a-z0-9-]{0,62}$`; anything else is
  rejected before touching Docker or the disk.
* **Runtime flags**: non-root user, `--cap-drop=ALL`,
  `--security-opt=no-new-privileges`, read-only root filesystem, `/tmp` as
  tmpfs, `--pids-limit`, `--memory`/`--memory-swap` equal, `--cpus`,
  no host mounts, no `--privileged`, no host network/PID/IPC namespaces.
* **Storage**: one Docker volume per job, deleted on stop. Size is enforced by
  a watcher that kills the job when it exceeds the seller's disk limit.
* **Network**: per-job bridge network with inter-container traffic disabled.
  Blocking access to the seller's LAN (RFC 1918, link-local) is required
  before public launch — tracked as a release blocker below.
* **GPU**: `--gpus` only when the seller enabled GPU sharing and the GPU check
  passes.
* **Limits**: a job is killed (event `killed_thermal`) when the GPU exceeds the
  seller's temperature ceiling for 30 s, and the node pauses until it cools.

## Release blockers before sellers get v2.0

1. LAN egress blocking for job networks, verified with a test container.
2. Windows code-signing certificate for the agent and installer (purchase
   needed — see README).
3. Backend `/ws/node/v1` live, old poll/reply endpoints removed.
4. The v1.0.0 GitHub release and its download links withdrawn.
