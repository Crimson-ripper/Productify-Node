"""Seller flow: create pairing code -> pair agent with it -> hardware fills in -> set price -> review."""
import asyncio, os, subprocess, sys, threading, time, json
backend, agent_exe, here = sys.argv[1], sys.argv[2], os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend); os.chdir(backend)
for k, v in {"MONGO_URL": "mongodb://localhost:1", "DB_NAME": "t", "JWT_SECRET": "x" * 40, "CORS_ORIGINS": "*",
             "ADMIN_EMAIL": "a@b.c", "ADMIN_PASSWORD": "p", "FRONTEND_URL": "http://x", "APP_NAME": "t"}.items():
    os.environ.setdefault(k, v)
import server, uvicorn
from fastapi.testclient import TestClient

STORE = {}
def match(d, q): return all(d.get(k) == v for k, v in (q or {}).items() if not isinstance(v, dict))
class Cursor:
    def __init__(self, rows): self.rows = rows
    def sort(self, *a, **k): return self
    async def to_list(self, n): return [dict(r) for r in self.rows]
class Coll:
    def __init__(self, n): self.rows = STORE.setdefault(n, [])
    async def insert_one(self, d): self.rows.append(dict(d))
    async def find_one(self, q, proj=None): return next((dict(r) for r in self.rows if match(r, q)), None)
    def find(self, q=None, proj=None): return Cursor([r for r in self.rows if match(r, q)])
    async def count_documents(self, q=None): return sum(1 for r in self.rows if match(r, q))
    async def update_one(self, q, u, upsert=False):
        for r in self.rows:
            if match(r, q): r.update(u.get("$set", {})); return
    async def delete_one(self, q): self.rows[:] = [r for r in self.rows if not match(r, q)]
class DB:
    def __getattr__(self, n): return Coll(n)
server.db = DB()
async def _noop(*a, **k): return None
server.node_manager.record_heartbeat = _noop
server.app.router.on_startup.clear(); server.app.router.on_shutdown.clear()

SELLER = {"id": "u-seller", "role": "seller", "name": "Asha", "email": "a@x", "seller_tier": "free"}
OTHER = {"id": "u-other", "role": "seller", "name": "Mallory", "email": "m@x"}
who = {"user": SELLER}
server.app.dependency_overrides[server.current_user] = lambda: who["user"]

PORT = 8766
srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=PORT, log_level="warning", lifespan="off"))
threading.Thread(target=lambda: asyncio.run(srv.serve()), daemon=True).start()
for _ in range(100):
    if srv.started: break
    time.sleep(0.1)
api = TestClient(server.app)

fails = 0
def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else "")); fails += 0 if cond else 1

# 1. Seller creates a machine: no specs, no image.
m = api.post("/api/seller/machines").json()
code = m.get("pairing_code", "")
check("pairing code issued", m.get("status") == "awaiting_pairing" and code.startswith(m["id"] + ".ptok_"), m)
check("publish before pairing refused", api.post(f"/api/seller/machines/{m['id']}/publish", json={"price": 0.4}).status_code == 400)
lst = api.get("/api/seller/listings").json()["rentals"]
check("listings show the code", lst and lst[0]["pairing_code"] == code)
check("not in public rentals", all(r["id"] != m["id"] for r in api.get("/api/rentals").json()))

# 2. Pair the real agent with just the code.
cfg = os.path.join(here, "node-mf.json")
json.dump({"backend_url": f"http://127.0.0.1:{PORT}", "memory_mb": 2048, "cpus": 2, "disk_gb": 10, "max_gpu_temp_c": 80}, open(cfg, "w"))
env = {**os.environ, "PRODUCTIFY_NODE_CONFIG": cfg, "PRODUCTIFY_DOCKER": os.path.join(here, "fake-docker.bat")}
agent = subprocess.Popen([agent_exe, "run"], env=env, stderr=subprocess.DEVNULL)
time.sleep(1.5)
bad = subprocess.run([agent_exe, "pair", "--code", m["id"] + ".ptok_0000000000000000"], env=env, capture_output=True, text=True)
time.sleep(3)
check("forged code doesn't fill in hardware", STORE["rentals"][0]["status"] == "awaiting_pairing")
subprocess.run([agent_exe, "pair", "--code", code], env=env, capture_output=True, text=True)

# 3. Hardware fills in by itself.
r = None
for _ in range(50):
    r = STORE["rentals"][0]
    if r["status"] == "paired": break
    time.sleep(0.2)
check("status -> paired after the agent connects", r["status"] == "paired", r["status"])
check("hardware recorded from the machine", r["gpu"] and r["specs"].get("cpu") and r["specs"].get("ram") and r.get("is_verified"), r.get("specs"))
check("title defaults to the GPU name", r["title"] == r["gpu"])
print("     detected:", r["gpu"], "|", r["specs"].get("cpu_model"), "|", r["specs"].get("cpu"), "|", r["specs"].get("ram"))

# 4. Another seller can't touch it.
who["user"] = OTHER
check("other seller can't publish it", api.post(f"/api/seller/machines/{m['id']}/publish", json={"price": 9}).status_code == 404)
check("other seller can't delete it", api.delete(f"/api/seller/machines/{m['id']}").status_code == 404)
who["user"] = SELLER

# 5. Seller sets a price -> review.
check("price must be positive", api.post(f"/api/seller/machines/{m['id']}/publish", json={"price": 0}).status_code == 422)
p = api.post(f"/api/seller/machines/{m['id']}/publish", json={"price": 0.35, "location": "Delhi, IN"}).json()
check("submitted for review", p.get("status") == "pending" and p.get("price") == 0.35 and p.get("location") == "Delhi, IN", p)
check("in-review machine can't be deleted", api.delete(f"/api/seller/machines/{m['id']}").status_code == 400)

# 6. A second, never-paired machine can be deleted.
m2 = api.post("/api/seller/machines").json()
check("unpaired machine deleted", api.delete(f"/api/seller/machines/{m2['id']}").json().get("ok") and len(STORE["rentals"]) == 1)

agent.kill()
srv.should_exit = True
sys.exit(1 if fails else 0)
