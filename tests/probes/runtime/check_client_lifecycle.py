import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, gc, weakref, threading, httpx
from http.server import ThreadingHTTPServer as HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length","2"); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self,*a): pass
srv=HTTPServer(("127.0.0.1",0),H); threading.Thread(target=srv.serve_forever,daemon=True).start()
url=f"http://127.0.0.1:{srv.server_port}/"
clients=weakref.WeakKeyDictionary()
async def call(close):
    loop=asyncio.get_running_loop()
    c=clients.get(loop)
    if c is None:
        c=clients[loop]=httpx.AsyncClient()
    r=await c.get(url)
    if close: await c.aclose()
    return r.status_code
for mode in (False,True):
    clients.clear()
    for i in range(5): asyncio.run(call(mode))
    gc.collect()
    print("aclose" if mode else "no-close", "entries surviving after 5 dead loops:", len(clients))
# no request made (client created only)
clients.clear()
async def noreq():
    clients[asyncio.get_running_loop()]=httpx.AsyncClient()
for i in range(5): asyncio.run(noreq())
gc.collect(); print("client created, no request:", len(clients))
