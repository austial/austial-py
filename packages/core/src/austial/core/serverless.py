"""Run an Austial application on AWS Lambda (API Gateway REST/HTTP APIs, Function URLs, ALB) through Mangum.

::

    # handler.py
    from austial import create_lambda_handler
    from src.app_module import AppModule

    handler = create_lambda_handler(AppModule)        # Lambda handler: "handler.handler"

The application is built once per cold start, outside the handler, and initialises (lifecycle hooks, async
providers) during the ASGI lifespan startup that Mangum runs on the first invocation. Needs ``pip install mangum``.
"""

from __future__ import annotations

from typing import Any


def create_lambda_handler(root_module: type, *, lifespan: str = "auto", **mangum_options: Any) -> Any:
    """Returns a ``handler(event, context)`` callable. ``mangum_options`` (``api_gateway_base_path``,
    ``text_mime_types``...) go to ``mangum.Mangum``; ``AustialFactory.create`` options are not exposed: build the
    application yourself and pass it to ``Mangum`` if you need them."""
    from austial.core.factory import AustialFactory  # deferred: factory imports the whole core package

    try:
        from mangum import Mangum
    except ImportError as exc:
        raise RuntimeError("create_lambda_handler needs Mangum: pip install mangum") from exc
    return Mangum(AustialFactory.create(root_module), lifespan=lifespan, **mangum_options)  # type: ignore[arg-type]
