"""``austial-worker`` -- run a worker, enqueue a job, or check status from the shell.

Bootstraps a minimal DI container from a product-supplied module path (e.g.
``src.app.app_module:AppModule``). The heavy DI lifting lives in ``austial.core``;
this file is glue that resolves the module, instantiates ``@Injectable`` classes
that carry ``@Cron``/``@Job`` metadata, and delegates to :class:`JobQueue` /
:class:`Worker`.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import signal
from pathlib import Path
from typing import Any

import typer

from austial.jobs.backend import InMemoryJobBackend
from austial.jobs.config import JobsConfig
from austial.jobs.idempotency import InMemoryIdempotencyStore
from austial.jobs.queue import JobQueue
from austial.jobs.registry import JobRegistry
from austial.jobs.worker import Worker

app = typer.Typer(
    name="austial-worker",
    help="Run and inspect the Austial job worker.",
    add_completion=False,
    no_args_is_help=True,
)


def _resolve_module(path: str) -> type:
    """``"pkg.mod:AttrName"`` -> the class object. Mirrors uvicorn's format."""
    if ":" not in path:
        raise typer.BadParameter("expected 'package.module:AttrName'")
    mod_path, attr = path.split(":", 1)
    module = importlib.import_module(mod_path)
    if not hasattr(module, attr):
        raise typer.BadParameter(f"{attr!r} not found in {mod_path!r}")
    return getattr(module, attr)


def _default_module_path() -> str:
    """The project's root module: ``src/app/app_module.py`` (the layout `austial new` writes), or the older flat
    ``src/app_module.py`` when that is all the current directory has. Looks at files, not imports: a console script
    doesn't put the working directory on ``sys.path`` until the module is imported."""
    src = Path("src")
    legacy_only = (src / "app_module.py").exists() and not (src / "app" / "app_module.py").exists()
    return "src.app_module:AppModule" if legacy_only else "src.app.app_module:AppModule"


def _bootstrap(module_cls: type) -> tuple[JobQueue, Worker, JobRegistry]:
    """Minimal wiring: pull providers off a ``@Module``-decorated class, honour a
    static ``for_root(...)``-shaped ``DynamicModule`` if present, instantiate
    the ``@Injectable`` classes we recognise, and register their ``@Job`` /
    ``@Cron`` methods. A real product boot uses the full DI container; this
    path is only for shell scripts (``austial-worker run ...``)."""
    from austial.common.decorators.modules import ModuleMetadata
    from austial.core.metadata import MODULE_METADATA, get_metadata

    metadata: ModuleMetadata | None = get_metadata(MODULE_METADATA, module_cls, None)
    providers: list[Any] = list(metadata.providers) if metadata else []

    backend = InMemoryJobBackend()
    idem = InMemoryIdempotencyStore()
    registry = JobRegistry()
    config = JobsConfig()

    instantiated: list[Any] = []
    for provider in providers:
        cls = provider if isinstance(provider, type) else None
        if cls is None:
            continue
        try:
            instance = cls()
        except TypeError:
            # Provider needs constructor args -- the full DI container handles
            # that; the CLI skips it here rather than guessing.
            continue
        instantiated.append(instance)
        registry.discover(instance)

    queue = JobQueue(backend=backend, registry=registry, idempotency=idem)
    worker = Worker(backend=backend, registry=registry, config=config)
    return queue, worker, registry


@app.command()
def run(
    module_path: str = typer.Argument(..., help="Product AppModule path, e.g. 'src.app.app_module:AppModule'."),
) -> None:
    """Start the worker loop against the product's ``AppModule``."""
    module_cls = _resolve_module(module_path)
    _, worker, _ = _bootstrap(module_cls)

    async def _main() -> None:
        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                # Windows / non-main threads don't support add_signal_handler.
                loop.add_signal_handler(sig, shutdown.set)
        typer.echo(f"austial-worker: running against {module_path}")
        await worker.run(shutdown=shutdown)

    asyncio.run(_main())


@app.command()
def status(
    job_id: str = typer.Argument(..., help="Job id returned by 'enqueue'."),
    module_path: str | None = typer.Option(
        None, "--module", help="Product AppModule path (default: src.app.app_module:AppModule)."
    ),
) -> None:
    """Print the current status of a single job."""
    module_cls = _resolve_module(module_path or _default_module_path())
    queue, _, _ = _bootstrap(module_cls)

    async def _main() -> None:
        state = await queue.status(job_id)
        if state is None:
            typer.echo(f"job {job_id}: not found")
            raise typer.Exit(code=1)
        typer.echo(f"job {job_id}: {state.value}")

    asyncio.run(_main())


@app.command()
def enqueue(
    name: str = typer.Argument(..., help="Name of the @Job to enqueue."),
    payload: str = typer.Option("{}", "--payload", help="JSON-encoded payload dict."),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="Deduplicate on this key."),
    module_path: str | None = typer.Option(
        None, "--module", help="Product AppModule path (default: src.app.app_module:AppModule)."
    ),
) -> None:
    """Enqueue a job by name from the shell (ops one-offs, backfills, seeding)."""
    module_cls = _resolve_module(module_path or _default_module_path())
    queue, _, _ = _bootstrap(module_cls)

    try:
        payload_dict = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON payload: {exc}") from exc
    if not isinstance(payload_dict, dict):
        raise typer.BadParameter("payload must decode to a JSON object")

    async def _main() -> str:
        return await queue.enqueue(name, payload=payload_dict, idempotency_key=idempotency_key)

    job_id = asyncio.run(_main())
    typer.echo(job_id)


if __name__ == "__main__":  # pragma: no cover
    app()
