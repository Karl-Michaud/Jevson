"""check_r3_sync_over_async.py — DESIGN §8 sync-over-async buildability.

Claim (DESIGN §8, Rev 5):
  "All are async; the synchronous resolve() runs them on a private event loop and
   refuses to run inside an already-running loop ... The backend owns one
   httpx.AsyncClient. The rate limiter is per API key, shared across every
   JevBackend in the process through a registry keyed by a hash of the key."

Method: a real local HTTP/1.1 keep-alive server (ThreadingHTTPServer, no Jev API).
  (a) one httpx.AsyncClient reused across two asyncio.run() calls (the naive
      "private event loop per resolve()" reading);
  (b) an asyncio.Semaphore / asyncio.Lock limiter shared across two loops, sequential
      and concurrent (two threads, each resolve() on its own loop);
  (c) calling a sync resolve() (asyncio.run) inside a running loop (Jupyter style);
  (d) candidate fixes: (d1) library-owned background loop thread + run_coroutine_threadsafe;
      (d2) per-call client created inside the loop; (d3) loop-agnostic threading token
      bucket shared across loops/threads, with concurrency and rate measured.
Output: results/r3/outputs/check_r3_sync_over_async.txt
"""
import asyncio, threading, time, sys, traceback, json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import httpx

OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); self.rfile.read(n)
        time.sleep(0.05)
        body = b'{"ok":true}'
        self.send_response(200); self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}/v1/ask"
log("python", sys.version.split()[0], "httpx", httpx.__version__)

def exc_str(e): return f"{type(e).__name__}: {e}"

# ---------- (a) one AsyncClient across two asyncio.run() ----------
log("\n== (a) one shared httpx.AsyncClient, resolve() = asyncio.run(...) twice ==")
client = httpx.AsyncClient()
async def ask(c): return (await c.post(URL, json={"q": 1})).status_code
for i in (1, 2, 3):
    try: log(f"  call {i}:", asyncio.run(ask(client)))
    except Exception as e: log(f"  call {i}: FAILED", exc_str(e))
# variant: new_event_loop per call, loop not closed
client2 = httpx.AsyncClient()
for i in (1, 2):
    loop = asyncio.new_event_loop()
    try: log(f"  new_event_loop (not closed) call {i}:", loop.run_until_complete(ask(client2)))
    except Exception as e: log(f"  new_event_loop call {i}: FAILED", exc_str(e))
# variant: two threads each running asyncio.run with the same client concurrently
client3 = httpx.AsyncClient(); res = {}
def worker(k):
    async def four(): return await asyncio.gather(*[ask(client3) for _ in range(4)])
    try: res[k] = asyncio.run(four())
    except Exception as e: res[k] = "FAILED " + exc_str(e)
ts = [threading.Thread(target=worker, args=(k,)) for k in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]
log("  two threads, one client, concurrent:", res)
for i in (1, 2):
    try: log(f"  same client afterwards, asyncio.run call {i}:", asyncio.run(ask(client3)))
    except Exception as e: log(f"  same client afterwards, asyncio.run call {i}: FAILED", exc_str(e))

# ---------- (b) asyncio-primitive limiter across loops ----------
log("\n== (b) asyncio.Semaphore/Lock limiter shared across loops ==")
sem = asyncio.Semaphore(1); lock = asyncio.Lock()
async def use(prim, hold=0.0):
    async with prim: await asyncio.sleep(hold); return "ok"
for name, prim in (("Semaphore(1)", sem), ("Lock", lock)):
    for i in (1, 2):
        try: log(f"  {name} sequential loop {i}:", asyncio.run(use(prim)))
        except Exception as e: log(f"  {name} sequential loop {i}: FAILED", exc_str(e))
# contention: loop A holds, loop B waits (in another thread) -> waiter future bound to B, released from A
for name, mk in (("Semaphore(1)", lambda: asyncio.Semaphore(1)), ("Lock", asyncio.Lock)):
    prim = mk(); r = {}
    def t(k, hold):
        t0 = time.monotonic()
        try: r[k] = (asyncio.run(asyncio.wait_for(use(prim, hold), 3)), f"returned after {time.monotonic()-t0:.2f}s")
        except Exception as e: r[k] = "FAILED " + exc_str(e)
    ta = threading.Thread(target=t, args=("A", 0.3)); tb = threading.Thread(target=t, args=("B", 0.0))
    ta.start(); time.sleep(0.05); tb.start(); ta.join(); tb.join()
    log(f"  {name} contended across two threads/loops (A holds 0.30s from t=0, B starts t=0.05):", r)
# same, but with no timeout: does B ever wake? (watchdog 5s)
for name, mk in (("Semaphore(1)", lambda: asyncio.Semaphore(1)), ("Lock", asyncio.Lock)):
    prim = mk(); r = {}
    def t2(k, hold):
        t0 = time.monotonic(); r[k] = (asyncio.run(use(prim, hold)), f"{time.monotonic()-t0:.2f}s")
    ta = threading.Thread(target=t2, args=("A", 0.3), daemon=True); tb = threading.Thread(target=t2, args=("B", 0.0), daemon=True)
    ta.start(); time.sleep(0.05); tb.start(); ta.join(); tb.join(5.0)
    log(f"  {name} contended, no timeout, 5s watchdog: A={r.get('A')} B={r.get('B', 'STILL BLOCKED after 5s (lost wakeup: release() from thread A scheduled the waiter on loop B with non-threadsafe call_soon)')}")
# contention within the same thread: many waiters in loop 1, then loop 2
prim = asyncio.Semaphore(2)
async def burst(p): return await asyncio.gather(*[use(p, 0.01) for _ in range(6)])
for i in (1, 2):
    try: log(f"  Semaphore(2) bursty loop {i}:", asyncio.run(burst(prim)))
    except Exception as e: log(f"  Semaphore(2) bursty loop {i}: FAILED", exc_str(e))

# ---------- (c) sync resolve() inside a running loop ----------
log("\n== (c) sync resolve() inside a running loop (Jupyter style) ==")
def resolve_naive():
    async def go():
        async with httpx.AsyncClient() as c: return await ask(c)
    return asyncio.run(go())
async def notebook_cell():
    try: return resolve_naive()
    except Exception as e: return "FAILED " + exc_str(e)
log("  asyncio.run inside running loop:", asyncio.run(notebook_cell()))
async def notebook_cell2():
    loop = asyncio.new_event_loop()
    try: return loop.run_until_complete(ask(httpx.AsyncClient()))
    except Exception as e: return "FAILED " + exc_str(e)
log("  new_event_loop().run_until_complete inside running loop:", asyncio.run(notebook_cell2()))

# ---------- (d) buildable designs ----------
log("\n== (d1) library-owned background loop thread; sync resolve() = run_coroutine_threadsafe ==")
class _LoopThread:
    _inst = None; _guard = threading.Lock()
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.t = threading.Thread(target=self.loop.run_forever, name="jevson-loop", daemon=True); self.t.start()
    @classmethod
    def get(cls):
        with cls._guard:
            if cls._inst is None: cls._inst = cls()
            return cls._inst
    def run(self, coro, timeout=None):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)
class Backend:  # owns one AsyncClient, created lazily on the background loop
    def __init__(self): self._client = None
    async def ask(self):
        if self._client is None: self._client = httpx.AsyncClient()
        return await ask(self._client)
b = Backend(); lt = _LoopThread.get()
log("  sync call 1:", lt.run(b.ask()), " sync call 2:", lt.run(b.ask()), " sync call 3:", lt.run(b.ask()))
r = {}
def w(k): r[k] = [lt.run(b.ask()) for _ in range(3)]
ts = [threading.Thread(target=w, args=(k,)) for k in range(4)]; [t.start() for t in ts]; [t.join() for t in ts]
log("  4 user threads x 3 sync calls, one client:", r)
async def cell(): return lt.run(b.ask(), timeout=5)  # sync resolve inside a running loop
try: log("  (d1) sync resolve() from inside a running loop:", asyncio.run(cell()), "(works, but blocks the caller's loop while waiting)")
except Exception as e: log("  (d1) inside running loop FAILED", exc_str(e))
# but aresolve() on the caller's loop must NOT use the background-loop client
async def aresolve_wrong(): return await b.ask()
try: log("  aresolve() on caller loop reusing background-loop client:", asyncio.run(aresolve_wrong()))
except Exception as e: log("  aresolve() on caller loop reusing background-loop client: FAILED", exc_str(e))

log("\n== (d2) per-loop client map (WeakKeyDictionary keyed by running loop) ==")
import weakref
class Backend2:
    def __init__(self): self._clients = weakref.WeakKeyDictionary()
    def _client(self):
        loop = asyncio.get_running_loop()
        c = self._clients.get(loop)
        if c is None: c = self._clients[loop] = httpx.AsyncClient()
        return c
    async def ask(self): return await ask(self._client())
b2 = Backend2()
out = []
for i in range(3):
    try: out.append(asyncio.run(b2.ask()))
    except Exception as e: out.append("FAILED " + exc_str(e))
log("  3 x asyncio.run with per-loop clients:", out, "(note: each dead loop leaves an unclosed client; needs aclose on loop shutdown)")

log("\n== (d3) loop-agnostic token bucket (threading.Lock + asyncio.sleep), shared across loops/threads ==")
class TokenBucket:
    def __init__(self, rate, burst):
        self.rate, self.cap, self.tokens, self.t = rate, burst, float(burst), time.monotonic()
        self._lk = threading.Lock()
    def _try(self):
        with self._lk:
            now = time.monotonic(); self.tokens = min(self.cap, self.tokens + (now - self.t) * self.rate); self.t = now
            if self.tokens >= 1: self.tokens -= 1; return 0.0
            return (1 - self.tokens) / self.rate
    async def acquire(self):
        while (w := self._try()) > 0: await asyncio.sleep(w)
_REG = {}; _REG_LK = threading.Lock()
def limiter_for(key_hash):
    with _REG_LK:
        return _REG.setdefault(key_hash, TokenBucket(rate=20, burst=5))
stamps = []; st_lk = threading.Lock()
async def limited_call():
    await limiter_for("k1").acquire()
    with st_lk: stamps.append(time.monotonic())
def thr():
    async def many(): await asyncio.gather(*[limited_call() for _ in range(15)])
    asyncio.run(many())
t0 = time.monotonic()
ts = [threading.Thread(target=thr) for _ in range(4)]; [t.start() for t in ts]; [t.join() for t in ts]
async def ten(): await asyncio.gather(*[limited_call() for _ in range(10)])
lt.run(ten())
el = time.monotonic() - t0; n = len(stamps)
log(f"  70 acquisitions from 5 loops (4 threads + background loop): elapsed {el:.2f}s; expected >= (70-5)/20 = {(70-5)/20:.2f}s; effective rate {(n-5)/el:.1f}/s (limit 20/s)")
stamps.sort(); maxwin = max(sum(1 for s in stamps if a <= s < a + 1.0) for a in stamps)
log(f"  max acquisitions in any 1s window: {maxwin} (<= burst+rate = 25)")

srv.shutdown()
open("/Users/karlosins/project-asterion/Jevson/scripts/redteam/results/r3/outputs/check_r3_sync_over_async.txt", "w").write("\n".join(OUT) + "\n")
