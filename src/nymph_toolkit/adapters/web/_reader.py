"""Bounded HTTP acquisition and HTML text extraction, with explicit origins."""

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from http.client import HTTPException
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from nymph_toolkit.contracts import OperationFailure

MAX_BYTES = 65536
READ_BUDGET = 3.0
BLOCK_TIMEOUT = 2.0
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", re.ASCII)


def origin(url):
    if (type(url) is not str or not url or len(url) > 2048 or "#" in url or "\\" in url
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)):
        raise ValueError("URL requires nonempty HTTP(S) text, at most 2048 characters, without fragments/controls")
    url.encode("ascii")  # Non-ASCII paths must be percent-encoded; hosts use IDNA.
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.netloc.endswith(":")):
        raise ValueError("URL requires an HTTP(S) host without credentials")
    port = parts.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("URL port must be in 1..65535")
    return parts.scheme, parts.hostname.lower(), port or (443 if parts.scheme == "https" else 80)


def origins(values):
    if type(values) is not list or not values:
        raise ValueError("allowed_origins requires a nonempty list")
    result = set()
    for value in values:
        item = origin(value)
        parts = urlsplit(value)
        if parts.path not in ("", "/") or "?" in value:
            raise ValueError("allowed_origins contain scheme/host/port only")
        result.add(item)
    return frozenset(result)


class _Text(HTMLParser):
    hidden = {"script", "style", "noscript", "template", "head", "iframe", "object"}
    blocks = {"p", "div", "br", "hr", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "header", "footer", "nav", "main", "pre", "blockquote", "ul", "ol"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skipped, self.parts = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.hidden:
            self.skipped.append(tag)
        if not self.skipped and tag in self.blocks:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.skipped:
            # Tolerate unclosed nested hidden tags without exposing their contents.
            index = len(self.skipped) - 1 - self.skipped[::-1].index(tag)
            del self.skipped[index:]
        if not self.skipped and tag in self.blocks | self.hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(data)

    def text(self):
        return "\n".join(line for raw in "".join(self.parts).splitlines() if (line := " ".join(raw.split())))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download(url, allowed):
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    deadline = time.monotonic() + READ_BUDGET
    current = url
    for redirects in range(4):
        if origin(current) not in allowed:
            return OperationFailure("web.origin", "URL origin is not allowed; no record saved")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        request = Request(current, headers={"User-Agent": "Nymph-Toolkit/1.4", "Accept": "text/plain,text/html", "Accept-Encoding": "identity"})
        try:
            response = opener.open(request, timeout=min(BLOCK_TIMEOUT, remaining))
        except HTTPError as error:
            with error:
                if error.code in (301, 302, 303, 307, 308):
                    location = error.headers.get("Location")
                    if redirects == 3 or not location:
                        return OperationFailure("web.redirect", "Redirect limit or missing location; no record saved")
                    current = urljoin(current, location)
                    continue
                return OperationFailure("web.http", f"HTTP status {error.code}; no record saved")
        with response:
            if response.status != 200:
                return OperationFailure("web.http", f"HTTP status {response.status}; no record saved")
            headers = response.headers
            mime = headers.get_content_type()
            charset = headers.get_content_charset()
            if (not headers.get("Content-Type") or mime not in ("text/plain", "text/html")
                    or charset not in (None, "utf-8", "utf8") or headers.get("Content-Encoding", "identity").lower() != "identity"):
                return OperationFailure("web.unsupported", "Only uncompressed UTF-8 text/plain or text/html is accepted")
            sizes = headers.get_all("Content-Length", [])
            if len(sizes) > 1 or (sizes and (not sizes[0].isascii() or not sizes[0].isdecimal())):
                return OperationFailure("web.read", "Invalid Content-Length; no record saved")
            expected = int(sizes[0]) if sizes else None
            if expected is not None and expected > MAX_BYTES:
                return OperationFailure("web.too_large", "Response exceeds 65536 bytes; no record saved")
            if expected is not None and headers.get("Transfer-Encoding"):
                return OperationFailure("web.read", "Ambiguous response length; no record saved")
            data = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError
                part = response.read1(min(4096, MAX_BYTES + 1 - len(data)))
                if time.monotonic() >= deadline:
                    raise TimeoutError
                if not part:
                    break
                data.extend(part)
                if len(data) > MAX_BYTES:
                    return OperationFailure("web.too_large", "Response exceeds 65536 bytes; no record saved")
            if expected is not None and len(data) != expected:
                return OperationFailure("web.read", "Response ended before Content-Length; no record saved")
            return bytes(data), mime, current
    raise AssertionError("Redirect loop must return or raise")


def read_record(request, allowed):
    try:
        if type(request) is not dict or set(request) != {"url", "record_id", "kind", "source_kind", "occurred_at"}:
            raise ValueError("request requires url, record_id, kind, source_kind, occurred_at")
        if any(type(v) is not str for v in request.values()):
            raise ValueError("request fields must be strings")
        for value in request.values():
            value.encode("utf-8")
        key = request["record_id"]
        if not key or key != key.strip() or len(key.encode("utf-8")) > 128:
            raise ValueError("record_id must be nonempty trimmed UTF-8 text of at most 128 bytes")
        if request["kind"] not in ("experience", "knowledge") or request["source_kind"] not in ("observed", "reported", "inferred", "imagined", "dream"):
            raise ValueError("Unknown kind or source_kind")
        stamp = request["occurred_at"]
        if not STAMP.fullmatch(stamp) or (not stamp.endswith("Z") and (int(stamp[-5:-3]) > 23 or int(stamp[-2:]) > 59)):
            raise ValueError("occurred_at requires valid RFC 3339 seconds and timezone")
        occurred = datetime.fromisoformat(stamp).astimezone(timezone.utc).isoformat()
        result = _download(request["url"], allowed)
        if isinstance(result, OperationFailure):
            return result
        data, mime, final_url = result
        text = data.decode("utf-8-sig")
        if mime == "text/html":
            parser = _Text()
            parser.feed(text)
            parser.close()
            text = parser.text()
        if not text.strip() or "\x00" in text:
            raise ValueError("Response must contain nonempty text without NUL")
        source = json.dumps({"url": request["url"], "final_url": final_url, "sha256": hashlib.sha256(data).hexdigest()}, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        record = dict(record_id=key, kind=request["kind"], content=text, source_kind=request["source_kind"], source=source, occurred_at=occurred)
        if len(json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")) > 4096:
            return OperationFailure("web.too_large", "Memory record exceeds 4096 JSON bytes; no record saved")
        return record
    except TimeoutError:
        return OperationFailure("web.timeout", "HTTP acquisition exceeded its deadline; no record saved")
    except URLError as error:
        code = "web.timeout" if isinstance(error.reason, TimeoutError) else "web.read"
        return OperationFailure(code, "HTTP acquisition failed; no record saved")
    except (ValueError, TypeError, OverflowError) as error:
        return OperationFailure("web.invalid", str(error))
    except (OSError, HTTPException):
        return OperationFailure("web.read", "HTTP acquisition failed; no record saved")
