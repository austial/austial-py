"""``StoredObject`` -- the value object every driver returns from ``put``,
``get``, ``stat`` and ``list``.

Represents the metadata about an object; ``data`` is only populated on ``get``
(streaming reads are outside this frozen shape -- drivers may add wrapper
methods later without breaking this type).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    content_type: str
    last_modified: datetime
    etag: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    data: bytes | None = None
