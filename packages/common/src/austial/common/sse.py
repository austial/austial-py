"""Server-Sent Events formatting for ``@Sse()`` handlers -- mirrors Nest's ``MessageEvent``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi.encoders import jsonable_encoder


@dataclass
class MessageEvent:
    data: Any
    id: str | None = None  # noqa: A003 - SSE field name
    type: str | None = None  # the SSE `event:` field
    retry: int | None = None  # reconnection time, milliseconds


def format_sse(event: Any) -> str:
    """Renders one event as an SSE frame (terminated by a blank line). ``event`` may be a
    ``MessageEvent``, a dict with a ``data`` key (plus optional ``id``/``type``/``event``/``retry``),
    or any other value, which becomes the ``data``. Non-string data is JSON-encoded."""
    if isinstance(event, MessageEvent):
        data, event_id, event_type, retry = event.data, event.id, event.type, event.retry
    elif isinstance(event, dict) and "data" in event:
        data = event["data"]
        event_id, retry = event.get("id"), event.get("retry")
        event_type = event.get("type", event.get("event"))
    else:
        data, event_id, event_type, retry = event, None, None, None

    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event_type is not None:
        lines.append(f"event: {event_type}")
    if retry is not None:
        lines.append(f"retry: {retry}")
    text = data if isinstance(data, str) else json.dumps(jsonable_encoder(data))
    lines.extend(f"data: {part}" for part in text.splitlines() or [""])
    return "\n".join(lines) + "\n\n"
