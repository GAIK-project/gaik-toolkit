"""Pseudonymisation with a keyed HMAC held by OpenBao / Vault transit.

Used when the collector forwards ``enduser.id`` instead of hashing it itself. The key never leaves the
vault: the sink sends identities to ``transit/hmac/<key>`` and stores only the result. Any failure
raises, so the caller refuses the batch and the raw identity is never stored.
"""

from __future__ import annotations

import base64
import json
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

RAW_ID = "enduser.id"
PSEUDO_ID = "enduser.pseudo.id"


class PseudonymError(Exception):
    pass


class TransitPseudonymiser:
    def __init__(self, addr: str, key: str, token_file: str, timeout: float = 5.0) -> None:
        self.url = f"{addr.rstrip('/')}/v1/transit/hmac/{key}/sha2-256"
        self.token_file = Path(token_file)
        self.timeout = timeout

    def __call__(self, values: list[str]) -> list[str]:
        # The token file is re-read on every call, so renewals by the agent are picked up.
        try:
            token = self.token_file.read_text().strip()
            body = {"batch_input": [{"input": base64.b64encode(v.encode()).decode()} for v in values]}
            req = urllib.request.Request(self.url, data=json.dumps(body).encode(), method="POST",
                                         headers={"X-Vault-Token": token, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                results = json.load(resp)["data"]["batch_results"]
        except Exception as exc:  # noqa: BLE001
            raise PseudonymError(f"transit HMAC failed: {exc}") from exc
        if len(results) != len(values) or any("hmac" not in r for r in results):
            raise PseudonymError("transit HMAC returned an incomplete batch")
        return [r["hmac"] for r in results]


def pseudonymise_payload(payload: dict[str, Any], hmac: Callable[[list[str]], list[str]]) -> None:
    """Replace every ``enduser.id`` attribute in an OTLP logs payload with ``enduser.pseudo.id``."""
    found: list[dict[str, Any]] = []
    for rl in payload.get("resourceLogs") or []:
        for sl in rl.get("scopeLogs") or []:
            for record in sl.get("logRecords") or []:
                for attr in record.get("attributes") or []:
                    if attr.get("key") == RAW_ID:
                        found.append(attr)
    if not found:
        return
    raw = [_scalar(a.get("value") or {}) for a in found]
    unique = sorted(set(raw))
    mapping = dict(zip(unique, hmac(unique), strict=True))
    for attr, value in zip(found, raw, strict=True):
        attr["key"] = PSEUDO_ID
        attr["value"] = {"stringValue": mapping[value]}


def _scalar(value: dict[str, Any]) -> str:
    for kind in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if kind in value:
            return str(value[kind])
    return json.dumps(value, sort_keys=True)
