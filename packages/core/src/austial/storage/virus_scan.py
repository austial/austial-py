"""Virus-scan hook contract.

The framework does not ship a real scanner -- ClamAV integration and
third-party APIs are product concerns. What it *does* ship is:

- a :class:`VirusScanHook` protocol that the product implements against its
  chosen scanner (ClamAV, VirusTotal, S3 GuardDuty, ...);
- a :class:`NoopVirusScan` reference implementation that always returns
  ``clean`` -- suitable for local dev and unit tests;
- a :class:`ScanResult` value object matching the ClamAV shape so hooks are
  drop-in replacements.

When configured, ``StorageService.put`` awaits the hook before writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from austial.common.decorators.injectable import Injectable


@dataclass(frozen=True, slots=True)
class ScanResult:
    """ClamAV-style result. ``signature`` is the virus name when infected."""

    clean: bool
    signature: str | None = None


@runtime_checkable
class VirusScanHook(Protocol):
    """Async hook called before every ``StorageService.put`` when configured."""

    async def scan(self, key: str, data: bytes) -> ScanResult: ...  # pragma: no cover


@Injectable()
class NoopVirusScan:
    """Reference implementation -- every payload is reported clean.

    Explicit hook (rather than allowing ``None``) so that a product that
    forgets to plug in a real scanner has to opt out in code, not by
    accident.
    """

    async def scan(self, key: str, data: bytes) -> ScanResult:
        return ScanResult(clean=True, signature=None)
