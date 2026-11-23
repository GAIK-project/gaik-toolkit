"""The id that owns a user's sessions, in place of their e-mail address.

The web app sends ``o_`` + the first 32 hex chars of an HMAC-SHA256 over the
lowercased, trimmed address (``solution_wizard_v2/lib/owner-id.ts``), so the
session rows, the session folders and the sandbox Jobs never hold the address.
This module computes the same id for the operator commands in
``session_admin``: finding a person's sessions from their address and moving
the sessions made before owner ids. A shared test vector keeps the two in step.

The key is the web app's: ``WIZARD_PSEUDONYM_KEY``, else
``NEXT_SERVER_ACTIONS_ENCRYPTION_KEY``. The api pod does not carry it; an
operator passes it for the one command that needs it. Without a key the id is
a plain SHA-256, as in the web app's local runs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

DOMAIN = "gaik-wizard-owner-id-v1"
OWNER_ID_RE = re.compile(r"^o_[0-9a-f]{32}$")
KEY_ENVS = ("WIZARD_PSEUDONYM_KEY", "NEXT_SERVER_ACTIONS_ENCRYPTION_KEY")


def owner_key() -> str | None:
    for name in KEY_ENVS:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def owner_id(email: str, key: str | None) -> str:
    """The owner id the web app sends for ``email`` under ``key``."""
    data = f"{DOMAIN}:{email.strip().lower()}".encode()
    if key:
        digest = hmac.new(key.encode(), data, hashlib.sha256).hexdigest()
    else:
        digest = hashlib.sha256(data).hexdigest()
    return f"o_{digest[:32]}"


def is_owner_id(value: str) -> bool:
    return bool(OWNER_ID_RE.match(value))


def is_address(value: str) -> bool:
    """A user id saved before owner ids: an e-mail address."""
    return "@" in value and not is_owner_id(value)
