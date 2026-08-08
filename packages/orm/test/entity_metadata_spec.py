"""Unit tests for ``@Entity()``'s decorator-time metadata construction -- table/column naming,
primary-key/relation detection, and dataclass field generation. No database involved.

Importing ``fixtures.entities`` at all is itself a regression check: ``Owner`` declares a
forward-referencing relation to ``Cat`` (defined later in that module) -- exactly the pattern
``@Entity()`` must resolve per-attribute rather than via one eager ``typing.get_type_hints(cls)``
call (see that module's docstring).
"""

from __future__ import annotations

import dataclasses

from fixtures.entities import Cat, Owner, Toy

from austial.orm.decorators.entity import get_entity_metadata
from austial.orm.metadata.entity_metadata import RelationType
from austial.orm.metadata.registry import MetadataRegistry


def test_table_names_are_snake_cased_class_names():
    assert get_entity_metadata(Owner).table_name == "owner"
    assert get_entity_metadata(Cat).table_name == "cat"
    assert get_entity_metadata(Toy).table_name == "toy"


def test_column_names_are_snake_cased_attribute_names():
    meta = get_entity_metadata(Cat)
    names = {c.attribute_name: c.column_name for c in meta.columns}
    assert names == {"id": "id", "name": "name", "age": "age", "created_at": "created_at"}


def test_primary_column_is_detected_and_marked_generated():
    meta = get_entity_metadata(Cat)
    assert [c.attribute_name for c in meta.primary_columns] == ["id"]
    assert meta.column("id").generated is True
    assert meta.column("id").primary is True


def test_many_to_one_and_one_to_many_pair_has_correct_owning_side():
    cat_meta = get_entity_metadata(Cat)
    owner_meta = get_entity_metadata(Owner)

    owner_rel = cat_meta.relation("owner")
    assert owner_rel is not None
    assert owner_rel.relation_type is RelationType.MANY_TO_ONE
    assert owner_rel.owning is True
    assert owner_rel.target() is Owner

    cats_rel = owner_meta.relation("cats")
    assert cats_rel is not None
    assert cats_rel.relation_type is RelationType.ONE_TO_MANY
    assert cats_rel.owning is False
    assert cats_rel.target() is Cat


def test_many_to_many_owning_side_carries_the_join_table():
    cat_meta = get_entity_metadata(Cat)
    toy_meta = get_entity_metadata(Toy)

    toys_rel = cat_meta.relation("toys")
    assert toys_rel is not None
    assert toys_rel.relation_type is RelationType.MANY_TO_MANY
    assert toys_rel.owning is True
    assert toys_rel.join_table is not None

    cats_rel = toy_meta.relation("cats")
    assert cats_rel is not None
    assert cats_rel.owning is False
    assert cats_rel.join_table is None


def test_entity_is_a_plain_dataclass_with_every_field_defaulted():
    assert dataclasses.is_dataclass(Cat)
    cat = Cat(name="Tom")
    assert cat.id is None
    assert cat.name == "Tom"
    assert cat.age is None
    assert cat.owner is None
    assert cat.toys == []


def test_to_many_relation_default_is_a_fresh_list_per_instance():
    first = Owner(name="Alice")
    second = Owner(name="Bob")
    first.cats.append(Cat(name="Tom"))
    assert second.cats == []


def test_metadata_registry_resolves_by_class():
    assert MetadataRegistry.get(Cat) is get_entity_metadata(Cat)
    assert MetadataRegistry.get_by_name(f"{Cat.__module__}.{Cat.__qualname__}") is get_entity_metadata(Cat)
