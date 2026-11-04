"""Loopback-only local HTTP demo. Not a public deployment server."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .core import TradeError
from .storage import Conflict, StorageError, Store


class Handler(BaseHTTPRequestHandler):
    server_version = "VirtualTradeLab/0.2"

    def log_message(self, *_args):
        pass  # Never log buyer data, request bodies, or the per-process CSRF token.

    def _send(self, status, body, mime="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def _state(self, value):
        return {**value, "csrf_token": self.server.csrf_token}

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "Loopback Host required."})
        path = urlsplit(self.path).path
        if path == "/api/state":
            try:
                return self._send(200, self._state(self.server.store.state()))
            except StorageError as exc:
                return self._send(503, {"error": str(exc)})
        files = {"/replay": ("replay.html", "text/html; charset=utf-8"),
                 "/replay.js": ("replay.js", "text/javascript; charset=utf-8"),
                 "/replay.css": ("replay.css", "text/css; charset=utf-8"),
                 "/replay-data.json": ("replay-data.json", "application/json; charset=utf-8"),
                 "/": ("index.html", "text/html; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path not in files:
            return self._send(404, {"error": "Not found."})
        name, mime = files[path]
        return self._send(200, (Path(__file__).parent / "web" / name).read_bytes(), mime)

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {"error": "Loopback Host required."})
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            return self._send(403, {"error": "Cross-origin request rejected."})
        if not secrets.compare_digest(self.headers.get("X-VTL-Token", "").encode(), self.server.csrf_token.encode()):
            return self._send(403, {"error": "Session changed. Refresh before acting."})
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._send(415, {"error": "JSON required."})
        if self.path not in {"/api/command", "/api/reset"}:
            return self._send(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise TradeError("Request size must be 1–65536 bytes.")
            payload = json.loads(self.rfile.read(length))
            fn = self.server.store.command if self.path == "/api/command" else self.server.store.reset
            self._send(200, self._state(fn(payload)))
        except Conflict as exc:
            self._send(409, {"error": str(exc)})
        except (TradeError, ValueError, UnicodeDecodeError, RecursionError) as exc:
            self._send(400, {"error": str(exc)})
        except StorageError as exc:
            self._send(503, {"error": str(exc)})

    def setup(self):
        super().setup()
        self.connection.settimeout(10)


def make_server(db, port=8765):
    store = Store(db)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.store = store
    server.csrf_token = secrets.token_urlsafe(32)
    return server


def main():
    parser = argparse.ArgumentParser(description="Local-only virtual trade UI; simulated credits, no payments")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1", help="loopback only")
    parser.add_argument("--strictPort", action="store_true", help="compatibility flag; port fallback is never used")
    parser.add_argument("--db", default=".virtual-trade-lab/state.sqlite3")
    args = parser.parse_args()
    try:
        server = make_server(args.db, args.port)
    except (StorageError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(f"Virtual Trade Lab (local only): http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Read-only model refund replay: http://127.0.0.1:{server.server_port}/replay", flush=True)
    print("Pure simulation. Database: " + str(server.store.path), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
