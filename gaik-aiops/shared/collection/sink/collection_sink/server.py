"""OTLP/HTTP (JSON) logs receiver that stores events in Postgres.

Sits behind the OpenTelemetry Collector, which owns privacy processing
(pseudonymisation, address masking). Configuration via environment:

    COLLECTION_DSN            Postgres DSN for a role with INSERT rights
    COLLECTION_DSN_FILE       Alternative: file containing the DSN (rendered by a vault agent)
    COLLECTION_LISTEN         host:port, default 0.0.0.0:4319
    AUDIT_RETENTION_DAYS      default 365 (placeholder until the customer decides)
    LOG_RETENTION_DAYS        default 30  (placeholder until the customer decides)
    PSEUDONYM_BACKEND         "collector" (default: the collector hashes) or "transit"
    OPENBAO_ADDR, OPENBAO_TOKEN_FILE, PSEUDONYM_TRANSIT_KEY   used with "transit"
"""

from __future__ import annotations

import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from collections.abc import Callable

from .otlp import Retention, parse_logs
from .pseudonym import PseudonymError, TransitPseudonymiser, pseudonymise_payload
from .store import Store

log = logging.getLogger("collection_sink")

MAX_BODY = 10 * 1024 * 1024


def make_handler(store: Store, retention: Retention,
                 pseudonymiser: Callable[[list[str]], list[str]] | None = None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/healthz":
                return self._reply(HTTPStatus.NOT_FOUND, {"error": "not found"})
            try:
                store.ping()
            except Exception:  # noqa: BLE001
                return self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "db unavailable"})
            self._reply(HTTPStatus.OK, {"status": "ok"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/v1/logs":
                return self._reply(HTTPStatus.NOT_FOUND, {"error": "not found"})
            if "json" not in (self.headers.get("Content-Type") or ""):
                return self._reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON only"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "bad length"})
            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return self._reply(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
            if pseudonymiser is not None:
                try:
                    pseudonymise_payload(payload, pseudonymiser)
                except PseudonymError:
                    log.exception("pseudonymisation failed")
                    # Fail closed: never store a raw identity; the collector retries.
                    return self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "pseudonymisation unavailable"})
            batch = parse_logs(payload, retention)
            try:
                store.write(batch)
            except Exception:  # noqa: BLE001
                log.exception("store write failed")
                # 503 tells the collector to retry with backoff instead of dropping.
                return self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "store unavailable"})
            body = {}
            if batch.rejected:
                body = {
                    "partialSuccess": {
                        "rejectedLogRecords": str(batch.rejected),
                        "errorMessage": "audit events require event.name",
                    }
                }
            self._reply(HTTPStatus.OK, body)

        def _reply(self, status: HTTPStatus, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            log.debug(fmt, *args)

    return Handler


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    host, _, port = os.environ.get("COLLECTION_LISTEN", "0.0.0.0:4319").rpartition(":")
    retention = Retention(
        audit_days=int(os.environ.get("AUDIT_RETENTION_DAYS", "365")),
        log_days=int(os.environ.get("LOG_RETENTION_DAYS", "30")),
    )
    dsn_file = os.environ.get("COLLECTION_DSN_FILE")
    store = Store(open(dsn_file).read().strip() if dsn_file else os.environ["COLLECTION_DSN"])
    pseudonymiser = None
    if os.environ.get("PSEUDONYM_BACKEND", "collector") == "transit":
        pseudonymiser = TransitPseudonymiser(os.environ["OPENBAO_ADDR"],
                                             os.environ.get("PSEUDONYM_TRANSIT_KEY", "audit-pseudonym"),
                                             os.environ["OPENBAO_TOKEN_FILE"])
    server = ThreadingHTTPServer((host, int(port)), make_handler(store, retention, pseudonymiser))
    log.info("listening on %s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
