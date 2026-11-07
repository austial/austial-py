"""``_to_fastapi_path``'s ``:name`` -> ``{name}`` translation, including the
``:name*`` catch-all convention used for path-shaped values like storage
keys (``@Get("files/:key*")`` must capture ``a/b/c.pdf`` as one ``key``, via
FastAPI's ``{key:path}`` converter). Guards against the substitution order
bug where a second plain-``:name`` pass over an already-substituted
``{key:path}`` re-matches the converter's own colon and corrupts it into
``{key{path}}``.
"""

from __future__ import annotations

import pytest

from austial.common.decorators.controllers import _to_fastapi_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", ""),
        (":id", "{id}"),
        ("users/:userId/posts/:postId", "users/{userId}/posts/{postId}"),
        ("files/:key*", "files/{key:path}"),
        (":key*", "{key:path}"),
        ("users/:userId*/posts/:postId", "users/{userId:path}/posts/{postId}"),
        ("a/:x*/b/:y*", "a/{x:path}/b/{y:path}"),
    ],
)
def test_to_fastapi_path(path: str, expected: str) -> None:
    assert _to_fastapi_path(path) == expected
