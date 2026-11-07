"""The module graph: who imports whom, what each module provides and exports.

It powers three things: strict module visibility (``AustialFactory.create(..., strict_modules=True)``),
``app.select(Module)``, and introspection -- ``to_dict()`` / ``to_mermaid()`` for devtools and the
``austial graph`` command.

Visibility follows NestJS: a provider can inject (a) what its own module provides, (b) what the modules
it imports *export* (a module can re-export an imported module by listing it in ``exports``), and
(c) what ``@Global`` modules export. Framework tokens (``ModuleRef``, ``REQUEST``, ...) are always visible.
"""

from __future__ import annotations

from typing import Any

from austial.core.container import ModuleRecord


class ModuleVisibilityError(Exception):
    def __init__(self, consumer: Any, token: Any, module: Any):
        consumer_name = getattr(consumer, "__name__", str(consumer))
        token_name = getattr(token, "__name__", str(token))
        module_name = getattr(module, "__name__", str(module))
        super().__init__(
            f"{consumer_name} (module {module_name}) can't inject {token_name}: {token_name} is provided by a module "
            f"that {module_name} doesn't import, or that doesn't export it. Import the module and add "
            f"{token_name} to its `exports=[...]` (or make the module @Global)."
        )
        self.consumer, self.token, self.module = consumer, token, module


def _name(obj: Any) -> str:
    return getattr(obj, "__name__", None) or str(obj)


class ModuleGraph:
    def __init__(self, records: list[ModuleRecord], always_visible: set[Any] | None = None):
        self.records = [r for r in records]
        self._by_module: dict[Any, ModuleRecord] = {r.module: r for r in self.records if r.module is not None}
        self._owners: dict[Any, list[ModuleRecord]] = {}
        for record in self.records:
            for token in [*record.providers, *record.controllers]:
                self._owners.setdefault(token, []).append(record)
        self._always = always_visible or set()
        self._visible_cache: dict[Any, set[Any]] = {}

    # -- visibility -------------------------------------------------------------------
    def exports_of(self, module: Any, _seen: frozenset = frozenset()) -> set[Any]:
        record = self._by_module.get(module)
        if record is None or module in _seen:
            return set()
        tokens: set[Any] = set()
        for exported in record.exports:
            if exported in self._by_module:  # a module in `exports` re-exports everything it exports
                tokens |= self.exports_of(exported, _seen | {module})
            else:
                tokens.add(exported)
        return tokens

    def visible_tokens(self, module: Any) -> set[Any]:
        if module in self._visible_cache:
            return self._visible_cache[module]
        record = self._by_module[module]
        visible = {*record.providers, *record.controllers}
        for imported in record.imports:
            visible |= self.exports_of(imported)
        for other in self.records:
            if other.is_global and other.module is not None:
                visible |= self.exports_of(other.module)
        self._visible_cache[module] = visible
        return visible

    def module_of(self, token: Any) -> Any:
        """The module that declares ``token`` (the first one, if several do), or ``None``."""
        owners = self._owners.get(token)
        return owners[0].module if owners else None

    def check(self, consumer: Any, token: Any) -> None:
        """Raises :class:`ModuleVisibilityError` unless ``consumer`` may inject ``token``."""
        if token in self._always or isinstance(token, str) and token in ("REQUEST", "INQUIRER"):
            return
        consumer_owners = self._owners.get(consumer)
        dependency_owners = self._owners.get(token)
        if not consumer_owners or not dependency_owners:
            return  # not declared in a module on one side: nothing to enforce
        for owner in consumer_owners:
            if owner.module is None:
                return
            visible = self.visible_tokens(owner.module)
            if token in visible:
                return
        raise ModuleVisibilityError(consumer, token, consumer_owners[0].module)

    def is_visible_from(self, module: Any, token: Any) -> bool:
        if module not in self._by_module:
            raise KeyError(f"{_name(module)} is not part of this application")
        return token in self._always or token in self.visible_tokens(module) or token not in self._owners

    # -- introspection ----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "modules": [
                {
                    "name": _name(r.module) if r.module is not None else "(dynamic)",
                    "global": r.is_global,
                    "imports": [_name(m) for m in r.imports],
                    "providers": [_name(t) for t in r.providers],
                    "controllers": [_name(t) for t in r.controllers],
                    "exports": [_name(t) for t in r.exports],
                }
                for r in self.records
            ]
        }

    def to_mermaid(self) -> str:
        """A Mermaid flowchart: an arrow ``A --> B`` means A imports B."""
        lines = ["flowchart LR"]
        for record in self.records:
            name = _name(record.module) if record.module is not None else "dynamic"
            label = f"{name}\\n{len(record.providers)} providers, {len(record.controllers)} controllers"
            lines.append(f'    {name}["{label}"]')
        for record in self.records:
            if record.module is None:
                continue
            for imported in record.imports:
                lines.append(f"    {_name(record.module)} --> {_name(imported)}")
        return "\n".join(lines)
