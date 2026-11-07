"""Mapped types -- mirrors ``@nestjs/mapped-types`` (``PartialType``, ``PickType``,
``OmitType``, ``IntersectionType``) for pydantic DTOs::

    class CreateCatDto(BaseModel):
        name: str
        age: int

    class UpdateCatDto(PartialType(CreateCatDto)): ...        # every field optional
    class CatNameDto(PickType(CreateCatDto, ["name"])): ...   # just `name`
    class CatPatchDto(OmitType(CreateCatDto, ["age"])): ...   # everything but `age`
    class CatDto(IntersectionType(CreateCatDto, TimestampsDto)): ...

Field definitions (types, defaults, ``Field(...)`` constraints) are carried over, so FastAPI's
validation and OpenAPI schema stay accurate. Validators (``@field_validator`` etc.) are *not*
carried over -- re-declare them on the subclass.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any, Optional

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo


def _fields_of(model: type[BaseModel]) -> dict[str, FieldInfo]:
    return dict(model.model_fields)


def _build(name: str, base: type[BaseModel], fields: dict[str, tuple[Any, Any]]) -> type[BaseModel]:
    model = create_model(name, __config__=base.model_config or None, **fields)  # type: ignore[call-overload]
    model.__doc__ = base.__doc__
    return model


def _clone(field: FieldInfo, *, optional: bool = False) -> tuple[Any, Any]:
    info = copy.copy(field)
    annotation: Any = field.annotation
    if optional:
        info.default = None
        info.default_factory = None
        annotation = Optional[annotation]  # noqa: UP045 - built dynamically from a runtime type
    return annotation, info


def PartialType(base: type[BaseModel]) -> type[BaseModel]:  # noqa: N802 - mirrors Nest
    """Every field of ``base`` becomes optional (default ``None``)."""
    return _build(f"Partial{base.__name__}", base, {n: _clone(f, optional=True) for n, f in _fields_of(base).items()})


def PickType(base: type[BaseModel], keys: Iterable[str]) -> type[BaseModel]:  # noqa: N802
    """Only ``keys`` of ``base``."""
    wanted = list(keys)
    fields = _fields_of(base)
    unknown = [k for k in wanted if k not in fields]
    if unknown:
        raise KeyError(f"PickType: {base.__name__} has no field(s) {unknown}")
    return _build(f"Pick{base.__name__}", base, {k: _clone(fields[k]) for k in wanted})


def OmitType(base: type[BaseModel], keys: Iterable[str]) -> type[BaseModel]:  # noqa: N802
    """Everything on ``base`` except ``keys``."""
    dropped = set(keys)
    fields = _fields_of(base)
    unknown = dropped - set(fields)
    if unknown:
        raise KeyError(f"OmitType: {base.__name__} has no field(s) {sorted(unknown)}")
    return _build(f"Omit{base.__name__}", base, {n: _clone(f) for n, f in fields.items() if n not in dropped})


def IntersectionType(*bases: type[BaseModel]) -> type[BaseModel]:  # noqa: N802
    """The union of every field of every base; later bases win on a name clash."""
    if len(bases) < 2:
        raise TypeError("IntersectionType needs at least two models")
    merged: dict[str, tuple[Any, Any]] = {}
    for base in bases:
        merged.update({n: _clone(f) for n, f in _fields_of(base).items()})
    return _build("Intersection" + "".join(b.__name__ for b in bases), bases[0], merged)
