"""``forward_ref`` -- mirrors Nest's ``forwardRef(() => Type)``.

Two things can be circular in a Nest app and both are supported here:

* **Providers**: ``Inject(forward_ref(lambda: B))`` as a constructor default hands the class a
  lazy proxy instead of the real instance, so ``A -> B -> A`` can be built. The proxy resolves
  the real provider on first attribute access (by which point the graph is fully built).
* **Modules**: ``imports=[forward_ref(lambda: BModule)]`` defers the import so two modules'
  files can reference each other without a Python-level circular import.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ForwardReference:
    __slots__ = ("_factory",)

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory

    def resolve(self) -> Any:
        return self._factory()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "forward_ref(...)"


def forward_ref(factory: Callable[[], Any]) -> ForwardReference:
    return ForwardReference(factory)


def unwrap(value: Any) -> Any:
    """Resolves a :class:`ForwardReference` to its target, passes anything else through."""
    return value.resolve() if isinstance(value, ForwardReference) else value


class LazyProvider:
    """Stand-in for a not-yet-constructed provider. Forwards attribute access, calls and
    ``repr`` to the real instance, resolved through the container on first use."""

    __slots__ = ("_container", "_token", "_target")

    def __init__(self, container: Any, token: Any) -> None:
        object.__setattr__(self, "_container", container)
        object.__setattr__(self, "_token", token)
        object.__setattr__(self, "_target", None)

    def _austial_target(self) -> Any:
        target = object.__getattribute__(self, "_target")
        if target is None:
            target = object.__getattribute__(self, "_container").resolve(object.__getattribute__(self, "_token"))
            object.__setattr__(self, "_target", target)
        return target

    def __getattr__(self, name: str) -> Any:
        return getattr(self._austial_target(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._austial_target(), name, value)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._austial_target()(*args, **kwargs)

    def __repr__(self) -> str:
        return f"LazyProvider({object.__getattribute__(self, '_token')!r})"
