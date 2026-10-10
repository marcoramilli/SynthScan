#!/usr/bin/env python3
"""Opt-in local HTTP API for ephemeral SynthScan audit and sanitize requests."""

import argparse
import hmac
import ipaddress
import json
import os
import tempfile
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from .risk import build_risk_payload
    from .sanitize import SOURCE_EXTENSIONS, _safe_relative_path, sanitize_text
    from .synthscan import PATTERNS_DEFAULT, SYNTHSCAN_VERSION, load_patterns, scan_directory
except ImportError:
    from risk import build_risk_payload
    from sanitize import SOURCE_EXTENSIONS, _safe_relative_path, sanitize_text
    from synthscan import PATTERNS_DEFAULT, SYNTHSCAN_VERSION, load_patterns, scan_directory


MAX_BODY_BYTES = 512 * 1024
MAX_FILES = 32
MAX_FILE_BYTES = 64 * 1024
RATE_LIMIT = 30
RATE_WINDOW_SECONDS = 60
ACTIVE_REQUESTS = threading.BoundedSemaphore(4)
REQUEST_TIMESTAMPS: dict[str, deque] = defaultdict(deque)
RATE_LOCK = threading.Lock()


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_files(raw_files: object) -> list[dict[str, str]]:
    if not isinstance(raw_files, list) or not raw_files or len(raw_files) > MAX_FILES:
        raise ValueError(f"files must be a list of 1 to {MAX_FILES} entries")
    files = []
    seen = set()
    for item in raw_files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("content"), str):
            raise ValueError("each file requires string path and content fields")
        relative = _safe_relative_path(item["path"])
        if relative in seen:
            raise ValueError("duplicate file paths are not allowed")
        seen.add(relative)
        if Path(relative).suffix.lower() not in SOURCE_EXTENSIONS:
            raise ValueError(f"unsupported source file type: {relative}")
        if len(item["content"].encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
        files.append({"path": relative, "content": item["content"]})
    return files


def _allow_request(client_ip: str) -> bool:
    now = time.monotonic()
    with RATE_LOCK:
        requests = REQUEST_TIMESTAMPS[client_ip]
        while requests and now - requests[0] >= RATE_WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= RATE_LIMIT:
            return False
        requests.append(now)
    return True


class AuditRequestHandler(BaseHTTPRequestHandler):
    server_version = "SynthScanLocalAPI/1"

    def log_message(self, format_string: str, *args) -> None:
        # Never log request bodies or source content.
        super().log_message("%s", self.path)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        token = os.environ.get("SYNTHSCAN_API_TOKEN", "")
        if token:
            supplied = self.headers.get("Authorization", "")
            return hmac.compare_digest(supplied, f"Bearer {token}")
        return _is_loopback(self.client_address[0])

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route not in ("/v1/audit", "/v1/sanitize"):
            self._send_json(404, {"error": "not_found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        if not _allow_request(self.client_address[0]):
            self._send_json(429, {"error": "rate_limit_exceeded"})
            return
        if not ACTIVE_REQUESTS.acquire(blocking=False):
            self._send_json(503, {"error": "server_busy"})
            return
        try:
            self._handle_request(route)
        finally:
            ACTIVE_REQUESTS.release()

    def _handle_request(self, route: str) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(413 if content_length > MAX_BODY_BYTES else 400, {"error": "invalid_body_size"})
            return
        try:
            request = json.loads(self.rfile.read(content_length))
            files = validate_files(request.get("files") if isinstance(request, dict) else None)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json(400, {"error": "invalid_request", "detail": str(exc)})
            return

        if route == "/v1/sanitize":
            results = []
            for item in files:
                result = sanitize_text(item["content"])
                results.append({
                    "path": item["path"],
                    "patches": result["patches"],
                    "review_items": result["review_items"],
                    "diff": result["diff"],
                })
            self._send_json(200, {
                "api_version": "1",
                "applied": False,
                "retained_source": False,
                "files": results,
            })
            return

        try:
            with tempfile.TemporaryDirectory(prefix="synthscan-api-") as temporary:
                root = Path(temporary)
                for item in files:
                    target = root / item["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(item["content"], encoding="utf-8")
                patterns = load_patterns(PATTERNS_DEFAULT)
                result = scan_directory(str(root), patterns)
                risk_payload = build_risk_payload(result, SYNTHSCAN_VERSION, str(root))
                matches = [
                    {
                        "file": str(Path(match.file).relative_to(root)),
                        "line": match.line_number,
                        "category": match.category,
                        "severity": match.severity,
                        "score": match.score,
                    }
                    for match in result.matches
                ]
            self._send_json(200, {
                "api_version": "1",
                "retained_source": False,
                "risk_payload": risk_payload,
                "matches": matches,
                "metrics": {
                    "files_scanned": result.files_scanned,
                    "lines_scanned": result.lines_scanned,
                    "match_count": len(result.matches),
                },
            })
        except Exception:
            self._send_json(500, {"error": "audit_failed"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the opt-in local SynthScan audit API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    token = os.environ.get("SYNTHSCAN_API_TOKEN", "")
    if not _is_loopback(args.host) and len(token) < 32:
        parser.error("non-loopback bind requires SYNTHSCAN_API_TOKEN of at least 32 characters")
    if token and len(token) < 16:
        parser.error("SYNTHSCAN_API_TOKEN must be at least 16 characters")
    server = ThreadingHTTPServer((args.host, args.port), AuditRequestHandler)
    print(f"SynthScan API listening on {args.host}:{args.port}; source retention is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()