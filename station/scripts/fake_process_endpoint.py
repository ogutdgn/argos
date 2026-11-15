"""A local stand-in for the web app's processing endpoint (W2.2), for testing the recorder.

It accepts ``POST /api/conversations/process`` like the real one
(docs/structure.md, "Station → web handoff"): it checks the
``Authorization: Bearer <secret>`` header (401 if wrong) and the
``{"conversation_id": "<uuid>"}`` body (400 if bad), then answers with the next
status from ``--status`` (default 202 for every call). Nothing is processed.

Run it, then point the recorder at it (from station/)::

    .venv/bin/python scripts/fake_process_endpoint.py --secret test-secret --status 500,500,202
    ARGOS_WEB_URL=http://127.0.0.1:8765 STATION_API_SECRET=test-secret \\
        .venv/bin/python -m argos_station.recorder --notify 6f1c1b8e-0c5e-4a39-9a43-2d0e3f6a7b10

The unit tests (tests/test_recorder.py) start it on a free port with ``FakeEndpoint``.
"""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PATH = "/api/conversations/process"

BODIES = {
    200: {"status": "processed"},
    202: {"status": "processing"},
    400: {"error": "invalid_request"},
    401: {"error": "unauthorized"},
    404: {"error": "conversation_not_found"},
    500: {"error": "internal"},
}


@dataclass(frozen=True)
class Call:
    authorization: str | None
    body: str
    status: int  # what it answered


class FakeEndpoint:
    """The stand-in server on a background thread. ``statuses``: answers in order; the last one repeats."""

    def __init__(self, secret: str, statuses: list[int] | None = None, host: str = "127.0.0.1", port: int = 0):
        self.secret = secret
        self.statuses = deque(statuses or [202])
        self.calls: list[Call] = []
        self._lock = threading.Lock()
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server's name
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8", "replace")
                auth = self.headers.get("Authorization")
                status, payload = endpoint._answer(self.path, auth, body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:  # quiet
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def _answer(self, path: str, auth: str | None, body: str) -> tuple[int, dict]:
        with self._lock:
            if path != PATH:
                status, payload = 404, {"error": "not_found"}
            elif auth != f"Bearer {self.secret}":
                status, payload = 401, BODIES[401]
            else:
                try:
                    conversation_id = str(uuid.UUID(json.loads(body)["conversation_id"]))
                except (ValueError, KeyError, TypeError, AttributeError):
                    status, payload = 400, BODIES[400]
                else:
                    status = self.statuses[0] if len(self.statuses) == 1 else self.statuses.popleft()
                    payload = dict(BODIES.get(status, {}))
                    if status in (200, 202):
                        payload = {"conversation_id": conversation_id, **payload}
            self.calls.append(Call(auth, body, status))
            return status, payload

    def start(self) -> FakeEndpoint:
        self._thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self) -> FakeEndpoint:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local stand-in for POST /api/conversations/process.")
    parser.add_argument("--secret", required=True, help="the STATION_API_SECRET it accepts (use a test value)")
    parser.add_argument("--port", type=int, default=8765, help="default 8765")
    parser.add_argument("--status", default="202",
                        help="comma-separated answers in order, the last one repeats (e.g. 500,500,202). "
                             "Wrong secret → 401 and bad body → 400 regardless.")
    args = parser.parse_args()
    statuses = [int(s) for s in args.status.split(",") if s.strip()]
    endpoint = FakeEndpoint(args.secret, statuses, port=args.port)
    print(f"Stand-in endpoint on {endpoint.url}{PATH}, answering {statuses}. Ctrl+C to stop.")
    try:
        endpoint.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for call in endpoint.calls:
            print(f"  {call.status}  {call.body}")
        endpoint.server.server_close()


if __name__ == "__main__":
    main()
