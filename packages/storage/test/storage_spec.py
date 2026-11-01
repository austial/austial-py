"""``austial.storage`` unit tests.

Covers everything a product depends on when it plugs the storage abstraction
into a real controller:

- put/get round-trip; get returns bytes, content-type and metadata.
- stat, delete and list.
- path-safety: ``../foo``, absolute ``/etc/passwd`` and null bytes are rejected.
- content-type inference from suffix.
- max-size enforcement.
- signed URL round-trip; expired / tampered / method-mismatched are rejected.
- virus scanning: ``NoopVirusScan`` clean; a fake infected hook rejects with
  ``MalwareDetectedError``.
- ``StorageConfig`` validation of a too-short secret.
"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest

from austial.storage import (
    InvalidSignedUrlError,
    LocalDriver,
    MalwareDetectedError,
    NoopVirusScan,
    ObjectTooLargeError,
    PathTraversalError,
    ScanResult,
    SignedUrlService,
    StorageConfig,
    StorageService,
    VirusScanHook,
)

_SECRET = "x" * 40


def _service(
    base: Path,
    *,
    max_bytes: int = 10 * 1024 * 1024,
    virus_scan: VirusScanHook | None = None,
) -> StorageService:
    config = StorageConfig(
        signed_url_secret=_SECRET,
        driver="local",
        local_base_dir=base,
        max_object_size_bytes=max_bytes,
    )
    return StorageService(
        driver=LocalDriver(base),
        config=config,
        signed_urls=SignedUrlService(_SECRET),
        virus_scan=virus_scan,
    )


# ---------------------------------------------------------------------------
# put + get + stat + delete + list


@pytest.mark.asyncio
async def test_put_and_get_round_trip(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    stored = await svc.put("docs/a.txt", b"hello", metadata={"owner": "aayush"})
    assert stored.key == "docs/a.txt"
    assert stored.size == 5
    assert stored.content_type == "text/plain"

    fetched = await svc.get("docs/a.txt")
    assert fetched.data == b"hello"
    assert fetched.metadata == {"owner": "aayush"}
    assert fetched.etag is not None


@pytest.mark.asyncio
async def test_put_accepts_binary_stream(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    await svc.put("blob.bin", BytesIO(b"stream-bytes"))
    fetched = await svc.get("blob.bin")
    assert fetched.data == b"stream-bytes"


@pytest.mark.asyncio
async def test_stat_returns_metadata_without_body(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    await svc.put("logs/x.txt", b"1234", metadata={"tenant": "acme"})
    info = await svc.stat("logs/x.txt")
    assert info.size == 4
    assert info.metadata == {"tenant": "acme"}
    assert info.data is None


@pytest.mark.asyncio
async def test_delete_is_idempotent(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    await svc.put("gone.txt", b"x")
    await svc.delete("gone.txt")
    await svc.delete("gone.txt")  # must not raise


@pytest.mark.asyncio
async def test_list_yields_all_matching_prefix(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    await svc.put("a/1.txt", b"1")
    await svc.put("a/2.txt", b"22")
    await svc.put("b/3.txt", b"333")

    keys_a = sorted([o.key async for o in svc.list("a/")])
    assert keys_a == ["a/1.txt", "a/2.txt"]

    keys_all = sorted([o.key async for o in svc.list("")])
    assert keys_all == ["a/1.txt", "a/2.txt", "b/3.txt"]


# ---------------------------------------------------------------------------
# path safety


@pytest.mark.parametrize(
    "bad",
    [
        "../etc/passwd",
        "docs/../../etc/passwd",
        "/etc/passwd",
        "\\Windows\\system32\\config",
        "foo\x00bar",
        "",
        ".",
        "..",
        "C:/x",
    ],
)
@pytest.mark.asyncio
async def test_put_rejects_unsafe_keys(tmp_path: Path, bad: str) -> None:
    svc = _service(tmp_path)
    with pytest.raises(PathTraversalError):
        await svc.put(bad, b"x")


# ---------------------------------------------------------------------------
# content-type inference


@pytest.mark.asyncio
async def test_content_type_inferred_from_suffix(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    stored = await svc.put("report.pdf", b"%PDF-1.7")
    assert stored.content_type == "application/pdf"

    unknown = await svc.put("weird.bin", b"\x00\x01\x02")
    assert unknown.content_type == "application/octet-stream"


# ---------------------------------------------------------------------------
# max object size


@pytest.mark.asyncio
async def test_put_rejects_oversize_payload(tmp_path: Path) -> None:
    svc = _service(tmp_path, max_bytes=8)
    with pytest.raises(ObjectTooLargeError):
        await svc.put("big.bin", b"123456789")


# ---------------------------------------------------------------------------
# signed URLs


def test_signed_url_round_trip() -> None:
    svc = SignedUrlService(_SECRET)
    fragment = svc.issue("docs/a.txt", ttl=timedelta(minutes=5))
    svc.verify(fragment, "docs/a.txt", "GET")  # must not raise
    svc.verify(
        f"https://example.com/files/docs/a.txt{fragment}",
        "docs/a.txt",
        "GET",
    )


def test_signed_url_rejects_expired() -> None:
    svc = SignedUrlService(_SECRET)
    with pytest.raises(ValueError):
        svc.issue("docs/a.txt", ttl=timedelta(seconds=0))

    # Manufacture an authentically-signed fragment whose exp is firmly in the past.
    import base64
    import hashlib
    import hmac as _hmac

    exp = 1
    key = _SECRET.encode()
    digest = _hmac.new(key, f"GET\ndocs/a.txt\n{exp}".encode(), hashlib.sha256).digest()[:24]
    sig = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    expired = f"?exp={exp}&m=GET&sig={sig}"
    with pytest.raises(InvalidSignedUrlError):
        svc.verify(expired, "docs/a.txt", "GET")


def test_signed_url_rejects_tampered_signature() -> None:
    svc = SignedUrlService(_SECRET)
    fragment = svc.issue("docs/a.txt", ttl=timedelta(minutes=5))
    tampered = fragment.replace("sig=", "sig=AAAA")
    with pytest.raises(InvalidSignedUrlError):
        svc.verify(tampered, "docs/a.txt", "GET")


def test_signed_url_rejects_wrong_key() -> None:
    svc = SignedUrlService(_SECRET)
    fragment = svc.issue("docs/a.txt", ttl=timedelta(minutes=5))
    with pytest.raises(InvalidSignedUrlError):
        svc.verify(fragment, "docs/b.txt", "GET")


def test_signed_url_rejects_wrong_method() -> None:
    svc = SignedUrlService(_SECRET)
    fragment = svc.issue("docs/a.txt", ttl=timedelta(minutes=5), method="GET")
    with pytest.raises(InvalidSignedUrlError):
        svc.verify(fragment, "docs/a.txt", "PUT")


def test_signed_url_service_rejects_short_secret() -> None:
    with pytest.raises(ValueError):
        SignedUrlService("too-short")


# ---------------------------------------------------------------------------
# virus scanning


class _InfectedScan:
    async def scan(self, key: str, data: bytes) -> ScanResult:
        return ScanResult(clean=False, signature="EICAR-Test-Signature")


@pytest.mark.asyncio
async def test_noop_virus_scan_always_clean(tmp_path: Path) -> None:
    svc = _service(tmp_path, virus_scan=NoopVirusScan())
    stored = await svc.put("clean.txt", b"benign")
    assert stored.size == 6


@pytest.mark.asyncio
async def test_infected_virus_scan_rejects(tmp_path: Path) -> None:
    svc = _service(tmp_path, virus_scan=_InfectedScan())
    with pytest.raises(MalwareDetectedError) as excinfo:
        await svc.put("bad.txt", b"eicar-payload")
    assert "EICAR-Test-Signature" in str(excinfo.value)


# ---------------------------------------------------------------------------
# StorageConfig validation


def test_storage_config_rejects_short_secret(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        StorageConfig(
            signed_url_secret="short",
            driver="local",
            local_base_dir=tmp_path,
        )


def test_storage_config_requires_local_base_dir() -> None:
    with pytest.raises(ValueError):
        StorageConfig(signed_url_secret=_SECRET, driver="local", local_base_dir=None)


def test_storage_config_requires_s3_bucket() -> None:
    with pytest.raises(ValueError):
        StorageConfig(signed_url_secret=_SECRET, driver="s3", s3_bucket=None)
