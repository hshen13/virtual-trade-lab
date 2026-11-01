"""Actual loopback HTTP fixture tests; no deployed or external server."""
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from virtual_trade_lab.__main__ import SOURCE
from virtual_trade_lab.server import make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.server = make_server(self.path, port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.port = self.server.server_port
        self.host = f"127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        self.temp.cleanup()

    def http(self, method="GET", path="/api/state", payload=None, headers=None, raw=None):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        base_headers = {"Host": self.host}
        if method == "POST":
            base_headers.update({"Content-Type": "application/json", "X-VTL-Token": self.server.csrf_token,
                                 "Origin": "http://" + self.host})
        base_headers.update(headers or {})
        client.request(method, path, body=body, headers=base_headers)
        response = client.getresponse()
        data = response.read()
        response_headers = dict(response.getheaders())
        status = response.status
        client.close()
        if response_headers.get("Content-Type", "").startswith("application/json"):
            data = json.loads(data)
        return status, data, response_headers

    def command(self, action="quote", state=None, key="quote", payload=None):
        state = state or self.http()[1]
        body = {"epoch": state["epoch"], "expected_revision": state["revision"], "key": key,
                "action": action, "order_id": "one",
                "payload": {"source": SOURCE} if payload is None and action == "quote" else payload or {}}
        return body, self.http("POST", "/api/command", payload=body)

    def test_loopback_only_and_state_security_headers(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, data, headers = self.http()
        self.assertEqual(status, 200)
        self.assertEqual(data["revision"], 0)
        self.assertEqual(data["csrf_token"], self.server.csrf_token)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_wrong_host_blocked_on_reads_and_writes(self):
        for method in ["GET", "POST"]:
            status, _, _ = self.http(method, headers={"Host": "evil.example"}, payload={} if method == "POST" else None)
            self.assertEqual(status, 403)

    def test_wrong_origin_or_token_is_rejected(self):
        for headers in [{"Origin": "https://evil.example"}, {"Origin": "null"},
                        {"X-VTL-Token": "caf\u00e9"}, {"X-VTL-Token": "wrong"}, {"X-VTL-Token": ""}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.http("POST", "/api/command", payload={}, headers=headers)[0], 403)
        self.assertEqual(self.http()[1]["revision"], 0)

    def test_wrong_content_type_and_malformed_json(self):
        self.assertEqual(self.http("POST", "/api/command", payload={}, headers={"Content-Type": "text/plain"})[0], 415)
        for raw in [b"not json", b"\xff", b"", b"[]", b"null"]:
            with self.subTest(raw=raw):
                self.assertEqual(self.http("POST", "/api/command", raw=raw)[0], 400)
        self.assertEqual(self.http()[1]["revision"], 0)

    def test_deeply_nested_json_rejected(self):
        raw = b"[" * 2000 + b"0" + b"]" * 2000
        self.assertEqual(self.http("POST", "/api/command", raw=raw)[0], 400)
        self.assertEqual(self.http()[1]["revision"], 0)

    def test_static_ui_assets_are_available(self):
        for path, marker in [("/", b"Virtual Trade Lab"), ("/app.js", b"AbortController"),
                             ("/style.css", b"@media")]:
            with self.subTest(path=path):
                status, data, headers = self.http(path=path)
                self.assertEqual(status, 200)
                self.assertIn(marker, data)
                self.assertEqual(headers["Cache-Control"], "no-store")

    def test_oversized_request_rejected(self):
        self.assertEqual(self.http("POST", "/api/command", raw=b" " * 65537)[0], 400)

    def test_http_retry_and_stale_tab(self):
        initial = self.http()[1]
        body, (status, quoted, _) = self.command(state=initial)
        self.assertEqual(status, 200)
        self.assertEqual(quoted["revision"], 1)
        self.assertEqual(self.http("POST", "/api/command", payload=body)[1], quoted)
        _, (status, error, _) = self.command("cancel", state=initial, key="stale")
        self.assertEqual(status, 409)
        self.assertIn("error", error)
        self.assertEqual(self.http()[1]["revision"], 1)

    def test_http_invalid_transition_is_atomic(self):
        _, (_, quoted, _) = self.command()
        _, (status, _, _) = self.command("deliver", key="wrong-order", state=quoted)
        self.assertEqual(status, 400)
        self.assertEqual(self.http()[1], quoted)

    def test_http_reset_retry(self):
        _, (_, quoted, _) = self.command()
        payload = {"epoch": quoted["epoch"], "expected_revision": 1, "key": "reset"}
        status, reset, _ = self.http("POST", "/api/reset", payload=payload)
        self.assertEqual(status, 200)
        self.assertEqual(reset["revision"], 0)
        self.assertNotEqual(reset["epoch"], quoted["epoch"])
        self.assertEqual(self.http("POST", "/api/reset", payload=payload)[1], reset)

    def test_corruption_returns_503_without_reset(self):
        self.command()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE commands SET digest='corrupt'")
        status, error, _ = self.http()
        self.assertEqual(status, 503)
        self.assertIn("error", error)
        self.assertEqual(self.http("POST", "/api/reset", payload={"epoch": "x", "expected_revision": 0, "key": "reset"})[0], 503)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM commands").fetchone()[0], 1)

    def test_unknown_paths_and_directory_traversal_not_served(self):
        for path in ["/not-found", "/../storage.py", "/%2e%2e/storage.py", "/.virtual-trade-lab/state.sqlite3"]:
            with self.subTest(path=path):
                self.assertEqual(self.http(path=path)[0], 404)
        self.assertEqual(self.http("POST", "/unknown", payload={})[0], 404)


if __name__ == "__main__":
    unittest.main()
