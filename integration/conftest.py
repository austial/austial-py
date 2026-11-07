"""Print the traceback of any unhandled exception behind a 500 -- the live tests would otherwise only see
``Internal Server Error``."""

from __future__ import annotations

import traceback

import pytest

from austial.common.exceptions import HttpException
from austial.common.filters import all_exceptions_filter as module


@pytest.fixture(autouse=True)
def _trace_unhandled_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    original = module.AllExceptionsFilter.catch

    async def catch(self, exc, host):
        if not isinstance(exc, HttpException):
            traceback.print_exception(exc)
        return await original(self, exc, host)

    monkeypatch.setattr(module.AllExceptionsFilter, "catch", catch)
