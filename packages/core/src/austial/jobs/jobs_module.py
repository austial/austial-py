"""``JobsModule.for_root(...)`` -- provides ``JobQueue``, ``Worker``,
``JobRegistry``, ``JobBackend`` and ``IdempotencyStore``.

Product code overrides the backend and idempotency store with persistent
implementations (Postgres/Redis) by passing ``backend=...`` /
``idempotency=...`` -- the in-memory defaults are what the reference package
ships so a fresh install runs without external infrastructure.
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.jobs.backend import InMemoryJobBackend, JobBackend
from austial.jobs.config import JobsConfig
from austial.jobs.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from austial.jobs.queue import JobQueue
from austial.jobs.registry import JobRegistry
from austial.jobs.worker import Worker


@Module()
class JobsModule:
    """Import via ``JobsModule.for_root(JobsConfig(), ...)`` in ``AppModule``'s
    ``imports=[...]``. Registered ``@Global`` by default so any provider can
    inject ``JobQueue`` and ``JobRegistry``."""

    @staticmethod
    def for_root(
        config: JobsConfig | None = None,
        *,
        backend: JobBackend | type | None = None,
        idempotency: IdempotencyStore | type | None = None,
        is_global: bool = True,
    ) -> DynamicModule:
        config = config or JobsConfig()
        chosen_backend: JobBackend = backend if isinstance(backend, JobBackend) else InMemoryJobBackend()
        chosen_idem: IdempotencyStore = (
            idempotency if isinstance(idempotency, IdempotencyStore) else InMemoryIdempotencyStore()
        )

        providers: list[Any] = [
            {"provide": JobsConfig, "useValue": config},
            {"provide": JobBackend, "useValue": chosen_backend},
            {"provide": IdempotencyStore, "useValue": chosen_idem},
            JobRegistry,
            JobQueue,
            Worker,
        ]
        return DynamicModule(
            module=JobsModule,
            providers=providers,
            exports=[
                JobsConfig,
                JobBackend,
                IdempotencyStore,
                JobRegistry,
                JobQueue,
                Worker,
            ],
        )
