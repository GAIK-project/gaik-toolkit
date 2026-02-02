"""SSE (Server-Sent Events) utilities."""

import json


def sse_event(event_type: str, data: dict) -> str:
    """Format data as an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
