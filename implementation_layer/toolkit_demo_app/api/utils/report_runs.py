"""Runs of the Report Writer family go through the web app's route handlers.

The five run routes (report writer, report writer v2, source normalizer, knowledge
curator, knowledge synthesis) are the costliest calls the demo makes. Their per-user
report quota is kept in the web app's database, and only the web app's route handlers
(``app/api/*/run/route.ts``) check it. With ``REPORT_RUN_TOKEN`` set on both
deployments, the handlers send it in ``X-GAIK-Report-Run`` and these routes refuse a
run without it, so a run that skips the quota, for example a call from another pod
in the project, is refused here. The generic proxy in ``proxy.ts`` never forwards the
header. Without the variable the routes accept runs as before and say so once in the
log.

The Report Writer's own limits are also checked here, with the same variables and
defaults as ``lib/report-writer/limits.ts``.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

REPORT_RUN_HEADER = "x-gaik-report-run"
_warned = False


def require_report_run_grant(request: Request) -> None:
    """FastAPI dependency: refuse a run without the web app's run token, when one is set."""
    global _warned
    token = os.environ.get("REPORT_RUN_TOKEN", "")
    if not token:
        if not _warned:
            logger.warning(
                "REPORT_RUN_TOKEN is not set: report runs are accepted "
                "without the web app's quota check"
            )
            _warned = True
        return
    given = request.headers.get(REPORT_RUN_HEADER, "")
    if not hmac.compare_digest(given.encode(), token.encode()):
        raise HTTPException(status_code=403, detail="Start this run from the demo's page.")


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def report_writer_limits() -> dict[str, int]:
    """The Report Writer limits, read at call time like the web app reads them."""
    return {
        "max_upload_bytes": _positive_int("REPORT_WRITER_MAX_UPLOAD_MB", 100) * 1024 * 1024,
        "max_sections": _positive_int("REPORT_WRITER_MAX_SECTIONS", 12),
        "max_evidence_chars": _positive_int("REPORT_WRITER_MAX_EVIDENCE_CHARS", 200000),
    }
