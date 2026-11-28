"""Loopback-only browser process with bounded snapshots, deltas and history."""

# SPDX-License-Identifier: Apache-2.0
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

_ASSETS = {
    "/": ("viewer.html", "text/html; charset=utf-8"),
    "/viewer.css": ("viewer.css", "text/css; charset=utf-8"),
    "/viewer.js": ("viewer.js", "text/javascript; charset=utf-8"),
}
_GROUPS = ("modules", "usage", "reports", "connections", "activities")


def _merge(current, changes):
    for group, values in changes.items():
        section = current.setdefault(group, {})
        for key, value in values.items():
            if group == "reports":
                section[key] = value
            else:
                section[key] = dict(section.get(key, {}), **value)
        if group == "activities":
            while len(section) > 200:
                del section[next(iter(section))]


class View:
    def __init__(self, send):
        self.lock = threading.Lock()
        self.send = send
        self.revision = self.command_id = 0
        self.run_id, self.state = "", "new"
        self.current = {name: {} for name in _GROUPS}
        self.history, self.deltas = deque(maxlen=200), deque(maxlen=16)
        self.terminal, self.queries = {}, {}
        self.launcher = False
        self.snapshots = {}
        self.last_pulse = time.monotonic()
        self.active = None

    def apply(self, message):
        with self.lock:
            kind = message["type"]
            if kind == "setup":
                self.run_id, self.queries = message["run_id"], message["queries"]
                self.launcher = message.get("launcher") is True
                self.snapshots.clear()
            elif kind == "update":
                self.last_pulse = time.monotonic()
                self.state, self.terminal = message["state"], message["terminal"]
                changes = message["changes"]
                _merge(self.current, changes)
                events = list(message["events"])
                self.history.extend(events)
                self.revision += 1
                self.deltas.append((self.revision, changes, events))
                self.snapshots.clear()
            elif kind == "reply" and self.active is not None:
                identifier, event, replies = self.active
                if identifier == message["id"]:
                    replies.append(message["result"])
                    event.set()

    def snapshot(self, since):
        with self.lock:
            reset = since is None or not self.deltas or not self.deltas[0][0] - 1 <= since <= self.revision
            stalled = self.state not in ("stopped", "failed") and time.monotonic() - self.last_pulse >= 3
            key = (None if reset else since, stalled)
            if key in self.snapshots:
                return self.snapshots[key]
            delta = self.current if reset else {}
            events = deque(self.history if reset else (), maxlen=200)
            if not reset:
                for revision, changes, additions in self.deltas:
                    if revision > since:
                        _merge(delta, changes)
                        events.extend(additions)
            if "activities" in delta:
                # The time line shows 12 entries; the event history keeps its own 200-entry window.
                activities = dict(list(self.current["activities"].items())[-12:])
                delta = dict(delta, activities=activities)
            snapshot = {"run_id": self.run_id, "revision": self.revision,
                        "reset": reset, "state": self.state, "stalled": stalled,
                        "changes": delta, "events": list(events), "terminal": self.terminal,
                        "queries": self.queries}
            if self.launcher:
                snapshot["launcher"] = True
            encoded = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode()
            self.snapshots[key] = encoded
            return encoded

    def request(self, operation, arguments, *, launcher=False):
        with self.lock:
            allowed = ("start_runtime", "pause", "resume", "finish") if launcher else self.queries
            if type(operation) is not str or operation not in allowed or type(arguments) is not dict:
                return {"status": "invalid"}
            if launcher and not self.launcher:
                return {"status": "not_available"}
            if self.active is not None:
                return {"status": "busy"}
            self.command_id += 1
            identifier, event, replies = self.command_id, threading.Event(), []
            self.active = identifier, event, replies
        try:
            command = {"id": identifier, "operation": operation, "arguments": arguments}
            if launcher:
                command["launcher"] = True
            self.send(command)
            event.wait(3)
            return replies[0] if replies else {"status": "outcome_unknown"}
        except (OSError, ValueError):
            return {"status": "outcome_unknown"}
        finally:
            with self.lock:
                self.active = None


class Server(ThreadingHTTPServer):
    def __init__(self, view):
        super().__init__(("127.0.0.1", 0), Handler)
        self.view = view
        self.token = secrets.token_urlsafe(24)
        self.launcher_token = secrets.token_urlsafe(24)
        self.workers = threading.BoundedSemaphore(16)

    @property
    def host(self):
        return f"127.0.0.1:{self.server_port}"

    def process_request(self, request, address):
        if not self.workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.workers.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.workers.release()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        self.request.settimeout(4)
        super().setup()

    def log_message(self, *args):
        pass

    def respond(self, code, content=b"", mime="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                         "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.headers.get("Host") != self.server.host:
            self.respond(403)
            return
        url = urlsplit(self.path)
        if url.path == "/api/snapshot":
            value = parse_qs(url.query).get("since", [""])[0]
            since = int(value) if value.isascii() and value.isdecimal() and len(value) <= 15 else None
            self.respond(200, self.server.view.snapshot(since), "application/json")
        elif url.path in _ASSETS:
            name, mime = _ASSETS[url.path]
            page = Path(__file__).with_name(name).read_bytes()
            if url.path == "/":
                page = page.replace(b"__NTK_CONSOLE_TOKEN__", self.server.token.encode())
                page = page.replace(b"__NTK_LAUNCHER_TOKEN__", self.server.launcher_token.encode())
            self.respond(200, page, mime)
        else:
            self.respond(404)

    def do_POST(self):
        allowed_origin = "http://" + self.server.host
        launcher = self.path == "/api/launcher"
        header = "X-NTK-Launcher" if launcher else "X-NTK-Console"
        expected = self.server.launcher_token if launcher else self.server.token
        provided = self.headers.get(header, "")
        if ((not launcher and self.path != "/api/console")
                or (launcher and not self.server.view.launcher)
                or self.headers.get("Host") != self.server.host
                or self.headers.get("Origin") != allowed_origin
                or not provided.isascii() or not secrets.compare_digest(provided, expected)):
            self.close_connection = True
            self.respond(403)
            return
        if self.headers.get_content_type() != "application/json":
            self.close_connection = True
            self.respond(415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192 or self.headers.get("Transfer-Encoding") is not None:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
            if type(payload) is not dict or set(payload) != {"operation", "arguments"}:
                raise ValueError
        except (ValueError, OverflowError, RecursionError):
            self.close_connection = True
            self.respond(400)
            return
        result = self.server.view.request(payload["operation"], payload["arguments"], launcher=launcher)
        self.respond(200, json.dumps(result, ensure_ascii=False).encode(), "application/json")


def main():
    if hasattr(os, "nice"):
        try:
            os.nice(5)
        except OSError:
            pass

    def send(value):
        print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)

    view = View(send)
    with Server(view) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            send({"port": server.server_port})
            for line in sys.stdin.buffer:
                view.apply(json.loads(line))
        finally:
            server.shutdown()
            worker.join()


if __name__ == "__main__":
    main()
