from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.loopback_model_auth_bridge import Bridge


class _UpstreamHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        assert self.path == "/v1/chat/completions"
        assert self.headers["Authorization"] == "Bearer secret-proxy-key"
        assert self.headers["X-User-Id"] == "tester"
        payload = json.dumps({"echo": body}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _thread(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_bridge_adds_proxy_auth_without_exposing_it_to_the_caller() -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    upstream_thread = _thread(upstream)
    bridge = Bridge(
        ("127.0.0.1", 0),
        upstream=f"http://127.0.0.1:{upstream.server_port}",
        api_key="secret-proxy-key",
        user_id="tester",
    )
    bridge_thread = _thread(bridge)
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{bridge.server_port}/v1/chat/completions",
            data=b'{"model":"Kimi-K2.6"}',
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 200
            assert json.load(response) == {"echo": {"model": "Kimi-K2.6"}}
    finally:
        bridge.shutdown()
        upstream.shutdown()
        bridge_thread.join(timeout=2)
        upstream_thread.join(timeout=2)


def test_proxy_contract_rejects_missing_key(tmp_path: Path) -> None:
    from scripts.loopback_model_auth_bridge import _proxy_contract

    path = tmp_path / "proxy_info.json"
    path.write_text(json.dumps({"url": "http://proxy:8000"}), encoding="utf-8")

    try:
        _proxy_contract(path)
    except RuntimeError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("missing key was accepted")
