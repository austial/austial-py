"""Global entity-metadata registry.

``@Entity()`` (``decorators/entity.py``) both stashes an :class:`EntityMetadata` on the class
itself via ``set_metadata`` (the framework's own decorator-metadata convention, for anything
that already has a reference to the class) *and* registers it here, keyed by class and by
qualified name. The by-name index exists purely to resolve relation targets supplied as forward
references (``lambda: Comment``) once every entity involved has been imported and decorated --
``DataSource.__init__`` is the only other consumer of this registry.
"""

from __future__ import annotations

from austial.orm.metadata.entity_metadata import EntityMetadata


class MetadataRegistry:
    _by_class: dict[type, EntityMetadata] = {}
    _by_qualname: dict[str, EntityMetadata] = {}

    @classmethod
    def register(cls, entity_cls: type, metadata: EntityMetadata) -> None:
        cls._by_class[entity_cls] = metadata
        cls._by_qualname[f"{entity_cls.__module__}.{entity_cls.__qualname__}"] = metadata

    @classmethod
    def get(cls, entity_cls: type) -> EntityMetadata | None:
        return cls._by_class.get(entity_cls)

    @classmethod
    def get_by_name(cls, qualname: str) -> EntityMetadata | None:
        return cls._by_qualname.get(qualname)

    @classmethod
    def all(cls) -> list[EntityMetadata]:
        return list(cls._by_class.values())

    @classmethod
    def clear(cls) -> None:
        """Test-only escape hatch -- resets the registry between test modules that redefine
        entities with the same class/module name."""
        cls._by_class.clear()
        cls._by_qualname.clear()
