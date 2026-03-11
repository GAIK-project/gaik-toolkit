"""SSE (Server-Sent Events) utilities."""

import json
from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse


def sse_event(event_type: str, data: dict) -> str:
    """Format data as an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


def sse_error_response(message: str) -> StreamingResponse:
    """Return a StreamingResponse that emits a single SSE error event."""

    async def _generate() -> AsyncGenerator[str, None]:
        yield sse_event("error", {"message": message})

    return StreamingResponse(_generate(), media_type="text/event-stream")
