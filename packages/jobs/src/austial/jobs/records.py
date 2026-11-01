"""``JobStatus`` enum and ``JobRecord`` value object.

Records are frozen dataclasses -- the backend replaces a record when the
status changes, so external consumers holding an older reference still see
the state at read time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    """Lifecycle of a job through the queue.

    - ``pending`` -- accepted by the queue, waiting for its ``run_at``.
    - ``running`` -- a worker has claimed it.
    - ``succeeded`` -- the handler returned normally.
    - ``failed`` -- retries exhausted; the last error is recorded.
    - ``cancelled`` -- explicitly cancelled before it started running.
    """

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A single job's persisted state."""

    id: str
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    status: JobStatus = JobStatus.pending
    run_at: datetime | None = None
    next_attempt_at: datetime | None = None
    error: str | None = None
