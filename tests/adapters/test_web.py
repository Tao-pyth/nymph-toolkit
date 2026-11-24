"""B04 HTTP behavior against real sockets, independent of the Memory store."""

# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
from unittest.mock import patch

from nymph_toolkit.contracts import OperationFailure
from nymph_toolkit.adapters.web._reader import MAX_BYTES, origin, origins, read_record

PLAIN = "猫 は 眠る".encode("utf-8")
HTML = '<html><head><title>hidden</title><style>hidden</style></head><body><p>猫 <b>は</b> 眠る</p><script>bad()</script><noscript>hidden</noscript><template>hidden</template><p>A &amp; B</p></body></html>'.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.calls.append(self.path)
        try:
            self.respond()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def respond(self):
        path = self.path
        if path == "/slow":
            time.sleep(.15)
        if path.startswith("/redirect") or path == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop" if path == "/loop" else self.server.redirect)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/status":
            self.send_error(503)
            return
        data = HTML if path == "/html" else PLAIN
        if path == "/invalid-utf8": data = b"\xff"
        if path == "/nul": data = b"a\x00b"
        if path == "/empty": data = b" \n "
        if path == "/model-too-large": data = b"a" * 4096
        if path in ("/big", "/big-unbounded"): data = b"a" * (MAX_BYTES + 1)
        if path == "/trickle": data = b"abcdefghijklmnopqrst"
        self.send_response(200)
        if path != "/missing-type":
            mime = "text/html" if path == "/html" else "application/pdf" if path == "/pdf" else "text/plain"
            self.send_header("Content-Type", mime + ("; charset=shift-jis" if path == "/charset" else "; charset=utf-8"))
        if path == "/compressed": self.send_header("Content-Encoding", "gzip")
        if path not in ("/big-unbounded", "/trickle"):
            self.send_header("Content-Length", str(len(data) + (100 if path == "/short" else 0)))
        self.end_headers()
        if path == "/trickle":
            for byte in data:
                self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(.02)
        else:
            self.wfile.write(data)


@contextmanager
def server():
    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    service.calls, service.redirect = [], "/plain"
    runner = threading.Thread(target=service.serve_forever, kwargs={"poll_interval": .01})
    runner.start()
    try:
        yield service, "http://127.0.0.1:" + str(service.server_port)
    finally:
        service.shutdown(); service.server_close(); runner.join()


def request(url):
    return dict(url=url, record_id="web-one", kind="experience", source_kind="observed", occurred_at="2026-11-24T21:00:00+09:00")


class WebReaderTests(unittest.TestCase):
    def test_plain_html_and_source_hash_redirect_preserve_original_and_final_url(self):
        with server() as (http, base):
            for path, content, raw in (("/plain", "猫 は 眠る", PLAIN), ("/html", "猫 は 眠る\nA & B", HTML), ("/redirect", "猫 は 眠る", PLAIN)):
                with self.subTest(path=path):
                    result = read_record(request(base+path), origins([base]))
                    self.assertIsInstance(result, dict, repr(result))
                    self.assertEqual(result["content"], content)
                    self.assertEqual(result["occurred_at"], "2026-11-24T12:00:00+00:00")
                    self.assertEqual(json.loads(result["source"]), {"url":base+path,"final_url":base+("/plain" if path=="/redirect" else path),"sha256":hashlib.sha256(raw).hexdigest()})
            self.assertEqual(http.calls, ["/plain", "/html", "/redirect", "/plain"])

    def test_origin_checks_initial_and_each_redirect_without_visiting_denied_target(self):
        with server() as (source, base), server() as (target, other):
            allowed = origins([base])
            self.assertEqual(read_record(request(other+"/plain"), allowed).code, "web.origin")
            source.redirect = other+"/plain"
            self.assertEqual(read_record(request(base+"/redirect"), allowed).code, "web.origin")
            self.assertEqual(target.calls, [])
            self.assertEqual(read_record(request(base+"/loop"), allowed).code, "web.redirect")
            self.assertEqual(source.calls, ["/redirect"] + ["/loop"] * 4)

    def test_negative_http_cases_return_no_record_and_do_not_retry(self):
        cases = {"/status":"http", "/pdf":"unsupported", "/charset":"unsupported", "/compressed":"unsupported", "/missing-type":"unsupported",
                 "/invalid-utf8":"invalid", "/nul":"invalid", "/empty":"invalid", "/model-too-large":"too_large", "/big":"too_large", "/big-unbounded":"too_large", "/short":"read"}
        with server() as (http, base):
            for path, code in cases.items():
                with self.subTest(path=path):
                    result = read_record(request(base+path), origins([base]))
                    self.assertIsInstance(result, OperationFailure, repr(result))
                    self.assertEqual(result.code, "web."+code)
            self.assertEqual(http.calls, list(cases))

    def test_blocking_timeout_and_total_read_budget(self):
        with server() as (http, base):
            with patch("nymph_toolkit.adapters.web._reader.BLOCK_TIMEOUT", .04):
                self.assertEqual(read_record(request(base+"/slow"), origins([base])).code, "web.timeout")
            with patch("nymph_toolkit.adapters.web._reader.READ_BUDGET", .08):
                self.assertEqual(read_record(request(base+"/trickle"), origins([base])).code, "web.timeout")
            self.assertEqual(http.calls, ["/slow", "/trickle"])

    def test_invalid_inputs_before_network_and_proxy_not_inherited(self):
        for url in ("ftp://example.com/a", "http://user:password@example.com/a", "http://example.com/#", "http://example.com:0/a", "http://example.com:99999/a", "http://example.com:/a", "http://example.com/\n", "http://example.com/文", "http://example.com/\\a"):
            with self.subTest(url=url), self.assertRaises((ValueError, UnicodeError)):
                origin(url)
        for value in ([], "http://example.com", ["http://example.com/path"], ["http://example.com?x"]):
            with self.assertRaises(ValueError): origins(value)
        self.assertEqual(origin("http://EXAMPLE.COM:80/path"), ("http", "example.com", 80))
        with server() as (http, base):
            for change in (dict(record_id=" "), dict(kind="bad"), dict(occurred_at="2026-11-24T00:00:00+24:00"), dict(extra="x")):
                self.assertEqual(read_record(dict(request(base), **change), origins([base])).code, "web.invalid")
            self.assertEqual(http.calls, [])
            with patch.dict("os.environ", {"http_proxy":"http://127.0.0.1:1", "HTTP_PROXY":"http://127.0.0.1:1", "no_proxy":"", "NO_PROXY":""}):
                self.assertIsInstance(read_record(request(base+"/plain"), origins([base])), dict)
