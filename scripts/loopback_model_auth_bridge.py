#!/usr/bin/env python3
"""Forward loopback model requests to one authenticated serve_api_v2 proxy."""

from __future__ import annotations

import argparse
import json
import os
import stat
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_BODY_BYTES = 16 * 1024 * 1024


def _proxy_contract(path: Path) -> tuple[str, str]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("proxy info must be a regular file")
    if info.st_size > 64 * 1024:
        raise RuntimeError("proxy info is unexpectedly large")
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("proxy info must contain one object")
    url = value.get("url")
    api_key = value.get("api_key")
    if not isinstance(url, str) or not isinstance(api_key, str) or not api_key:
        raise RuntimeError("proxy info is missing its URL or API key")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.query or parsed.fragment:
        raise RuntimeError("proxy URL must be a plain internal HTTP origin")
    return url.rstrip("/"), api_key


class Bridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        upstream: str,
        api_key: str,
        user_id: str,
    ) -> None:
        super().__init__(address, Handler)
        self.upstream = upstream
        self.api_key = api_key
        self.user_id = user_id
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Handler(BaseHTTPRequestHandler):
    server: Bridge

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_error(404)
            return
        payload = b'{"status":"ok"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(400)
            return
        if length < 1 or length > MAX_BODY_BYTES:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        request = urllib.request.Request(
            self.server.upstream + self.path,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + self.server.api_key,
                "Content-Type": "application/json",
                "X-User-Id": self.server.user_id,
            },
        )
        try:
            with self.server.opener.open(request, timeout=120) as response:
                payload = response.read(MAX_BODY_BYTES + 1)
                status = response.status
                content_type = response.headers.get(
                    "Content-Type", "application/json"
                )
        except urllib.error.HTTPError as error:
            payload = error.read(MAX_BODY_BYTES + 1)
            status = error.code
            content_type = error.headers.get("Content-Type", "application/json")
        except OSError:
            payload = b'{"error":{"message":"upstream unavailable"}}\n'
            status = 502
            content_type = "application/json"
        if len(payload) > MAX_BODY_BYTES:
            self.send_error(502)
            return
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy-info", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user-id", default=os.environ.get("USER", "aar"))
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit("port must be between 1024 and 65535")
    upstream, api_key = _proxy_contract(args.proxy_info.resolve(strict=True))
    server = Bridge(
        ("127.0.0.1", args.port),
        upstream=upstream,
        api_key=api_key,
        user_id=args.user_id,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
