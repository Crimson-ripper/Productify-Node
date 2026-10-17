"""Real backend (fake DB) + real Go agent binary, talking over /ws/node/v1."""
import asyncio, json, os, subprocess, sys, threading, time
from fastapi import HTTPException
backend, agent_exe, here = sys.argv[1], sys.argv[2], os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend); os.chdir(backend)
for k, v in {"MONGO_URL": "mongodb://localhost:1", "DB_NAME": "t", "JWT_SECRET": "x" * 40, "CORS_ORIGINS": "*",
             "ADMIN_EMAIL": "a@b.c", "ADMIN_PASSWORD": "p", "FRONTEND_URL": "http://x", "APP_NAME": "t"}.items():
    os.environ.setdefault(k, v)
import server, uvicorn

RENTAL = {"id": "r-abc123def4", "pairing_token": "ptok_0123456789abcdef", "status": "approved"}
class Coll:
    async def find_one(self, q, proj=None): return dict(RENTAL) if q.get("id") == RENTAL["id"] else None
    async def update_one(self, *a, **k): return None
    async def insert_one(self, *a, **k): return None
class DB:
    def __getattr__(self, n): return Coll()
server.db = DB()
async def _noop(*a, **k): return None
server.node_manager.record_heartbeat = _noop

server.app.router.on_startup.clear()   # skip DB seeding / storage init
server.app.router.on_shutdown.clear()
PORT = 8765
cfg = uvicorn.Config(server.app, host="127.0.0.1", port=PORT, log_level="warning", lifespan="off")
srv = uvicorn.Server(cfg)
loop_box = {}
def serve():
    loop = asyncio.new_event_loop(); loop_box["loop"] = loop
    loop.run_until_complete(srv.serve())
threading.Thread(target=serve, daemon=True).start()
for _ in range(100):
    if srv.started: break
    time.sleep(0.1)
else:
    sys.exit("backend didn't start")
loop = loop_box["loop"]
def call(coro, timeout=60): return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

fails = 0
def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else "")); fails += 0 if cond else 1

env = {**os.environ, "PRODUCTIFY_NODE_CONFIG": os.path.join(here, "node.json"), "PRODUCTIFY_DOCKER": os.path.join(here, "fake-docker.bat")}
for f in ("node.json", "docker-calls.log"):
    try: os.remove(os.path.join(here, f))
    except FileNotFoundError: pass
run = lambda *a: subprocess.run([agent_exe, *a], env=env, capture_output=True, text=True)

# Wrong token is refused and the agent gives up instead of hammering.
run("pair", "--rental", RENTAL["id"], "--token", "ptok_ffffffffffffffff", "--backend", f"http://127.0.0.1:{PORT}")
run("live", "on")
bad = subprocess.Popen([agent_exe, "run"], env=env, stderr=subprocess.PIPE, text=True)
time.sleep(4)
check("wrong token: not connected", not server.node_hub.is_connected(RENTAL["id"]))
bad.kill(); err = bad.stderr.read()
check("wrong token: agent reports pairing rejected", "rejected" in err, err[-300:])

# Correct token connects; backend drives a job through the legacy send_rpc path.
run("pair", "--rental", RENTAL["id"], "--token", RENTAL["pairing_token"], "--backend", f"http://127.0.0.1:{PORT}")
agent = subprocess.Popen([agent_exe, "run"], env=env, stderr=subprocess.PIPE, text=True)
for _ in range(50):
    if server.node_hub.is_connected(RENTAL["id"]): break
    time.sleep(0.2)
check("agent connected", server.node_hub.is_connected(RENTAL["id"]))
time.sleep(0.5)
meta = server.node_hub.meta.get(RENTAL["id"], {})
check("hello received", meta.get("agent_version") == "2.0.0-dev" and meta.get("docker") is True, meta)
check("host_tunnel_manager sees it online", server.host_tunnel_manager.is_connected(RENTAL["id"]))

m = server.host_tunnel_manager
r = call(m.send_rpc(RENTAL["id"], "deploy_pod", {"instance_id": "inst-e2e1", "template_id": "jupyter-pytorch"}))
check("deploy -> job.start ok", r.get("ok") and r.get("container_id") == "productify-job-inst-e2e1", r)
r = call(m.send_rpc(RENTAL["id"], "exec", {"instance_id": "inst-e2e1", "code": "print('hi')"}))
check("exec -> stdout from container", "hello from container" in r.get("stdout", ""), r)
for bad_action, payload in (("deploy_pod", {"instance_id": "inst-e2e2", "template_id": "ollama-llm"}),
                            ("launch_game_container", {"session_id": "s1"}),
                            ("deploy_pod", {"instance_id": "../../evil", "template_id": "ubuntu-base"})):
    try:
        call(m.send_rpc(RENTAL["id"], bad_action, payload)); check(f"refuses {bad_action} {payload}", False)
    except HTTPException as e:
        check(f"refuses {bad_action} {list(payload.values())[-1]}", e.status_code in (400, 502), e.detail)
r = call(m.send_rpc(RENTAL["id"], "destroy_pod", {"instance_id": "inst-e2e1"}))
check("destroy -> job.stop ok", r.get("ok"))

calls = open(os.path.join(here, "docker-calls.log")).read()
check("ran the pinned pytorch image", "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime@sha256:" in calls)
check("container locked down", "--cap-drop ALL" in calls and "--read-only" in calls and "--user 1000:1000" in calls)
check("no ../ path ever reached docker", "evil" not in calls)
check("exec used timeout + python", "timeout --signal=KILL 60 python3 -c" in calls)

# Pause from the seller side: new jobs refused.
run("live", "off")
time.sleep(3)  # the running agent re-reads settings every 2 s
try:
    call(m.send_rpc(RENTAL["id"], "deploy_pod", {"instance_id": "inst-e2e3", "template_id": "ubuntu-base"}))
    check("paused machine refuses jobs", False)
except HTTPException as e:
    check("paused machine refuses jobs", "paused" in str(e.detail), e.detail)

agent.kill()
time.sleep(1)
check("disconnect noticed", not server.node_hub.is_connected(RENTAL["id"]))
srv.should_exit = True
sys.exit(1 if fails else 0)
