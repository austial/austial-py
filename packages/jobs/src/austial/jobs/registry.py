"""``JobRegistry`` -- maps a job name to the bound method that runs it, and
holds the ``@Cron`` entries the worker fires on a schedule.

The registry is intentionally dumb: it stores callables, not classes. Product
code passes ``@Injectable``-resolved instances to :meth:`discover` after DI
bootstrap, and the registry walks each instance's methods reading the
``@Cron``/``@Job`` metadata. This keeps the module free of framework-internal
"bootstrap hook" plumbing (nothing here imports from ``austial.core`` beyond
the metadata helpers) and makes the registry trivial to test in isolation.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.core.metadata import get_metadata
from austial.jobs.decorators import CRON_METADATA, JOB_METADATA, CronSpec, JobSpec

JobCallable = Callable[..., Awaitable[Any] | Any]


@dataclass(frozen=True, slots=True)
class JobEntry:
    """One ``@Job``-decorated handler."""

    spec: JobSpec
    handler: JobCallable


@dataclass(frozen=True, slots=True)
class CronEntry:
    """One ``@Cron``-decorated handler. ``name`` is the enqueue name used to
    fire it (defaults to ``spec.name`` or the method's qualified name)."""

    spec: CronSpec
    handler: JobCallable
    name: str


@Injectable()
class JobRegistry:
    """DI-container-managed registry. Manual registration via :meth:`register_job` /
    :meth:`register_cron` for the small-scale case; :meth:`discover(instance)` for
    the "grab everything an injectable exposes" case."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobEntry] = {}
        self._crons: list[CronEntry] = []

    # -- manual registration -------------------------------------------------

    def register_job(self, spec: JobSpec, handler: JobCallable) -> None:
        if spec.name in self._jobs:
            raise ValueError(f"Job {spec.name!r} already registered")
        self._jobs[spec.name] = JobEntry(spec=spec, handler=handler)

    def register_cron(self, spec: CronSpec, handler: JobCallable, *, name: str | None = None) -> None:
        cron_name = name or spec.name or getattr(handler, "__qualname__", None) or handler.__name__
        self._crons.append(CronEntry(spec=spec, handler=handler, name=cron_name))

    # -- discovery -----------------------------------------------------------

    def discover(self, instance: Any) -> None:
        """Walk every method on ``instance``'s class and register the ones
        carrying ``@Job``/``@Cron`` metadata. Bound methods are stored so the
        registry captures ``self``."""
        cls = type(instance)
        for attr_name, attr in inspect.getmembers(cls, predicate=callable):
            if attr_name.startswith("_"):
                continue
            job_spec: JobSpec | None = get_metadata(JOB_METADATA, attr, None)
            cron_spec: CronSpec | None = get_metadata(CRON_METADATA, attr, None)
            if job_spec is None and cron_spec is None:
                continue
            bound = getattr(instance, attr_name)
            if job_spec is not None:
                self.register_job(job_spec, bound)
            if cron_spec is not None:
                self.register_cron(cron_spec, bound, name=cron_spec.name or job_spec.name if job_spec else None)

    # -- lookup --------------------------------------------------------------

    def get_job(self, name: str) -> JobEntry | None:
        return self._jobs.get(name)

    def all_jobs(self) -> list[JobEntry]:
        return list(self._jobs.values())

    def all_crons(self) -> list[CronEntry]:
        return list(self._crons)
