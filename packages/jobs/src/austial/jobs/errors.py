"""Job-specific exceptions.

These extend Austial's HTTP exceptions where the mapping is unambiguous so the
framework's ``AllExceptionsFilter`` produces a sensible response when a job
error surfaces through an HTTP endpoint (rare -- most job errors are caught
inside the worker's retry loop). Otherwise plain ``Exception`` subclasses.
"""

from __future__ import annotations

from austial.common.exceptions import BadRequestException, NotFoundException


class JobError(Exception):
    """Base for job-runtime errors."""


class UnknownJobError(NotFoundException):
    """Raised by ``JobQueue.enqueue`` when no ``@Job`` handler matches the name."""

    def __init__(self, name: str):
        super().__init__(f"No @Job handler registered for name={name!r}")
        self.name = name


class InvalidScheduleError(BadRequestException):
    """The schedule string could not be parsed."""

    def __init__(self, schedule: str, reason: str = ""):
        detail = f"Invalid schedule {schedule!r}"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(detail)
        self.schedule = schedule


class JobExecutionError(JobError):
    """Wraps the underlying exception the handler raised, together with the
    attempt number and job id for logging."""

    def __init__(self, job_id: str, attempt: int, cause: BaseException):
        super().__init__(f"Job {job_id} failed on attempt {attempt}: {cause!r}")
        self.job_id = job_id
        self.attempt = attempt
        self.cause = cause
