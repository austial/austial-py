"""``RowHydrator`` -- turns flat ``DriverResult`` rows (``{"cat__id": 1, "owner__id": 2, ...}``)
back into entity instances, including grouping fanned-out rows from eager-loaded to-many joins
(a ``LEFT JOIN`` against a to-many relation duplicates the root row once per child row) into a
single root instance with a populated list attribute.

Phase-1 limitation (matches ``QueryBuilder``/``FindOptions.relations``): only single-level
eager-loaded relations are hydrated -- a joined entity's own relations are never further
populated from the same result set.
"""

from __future__ import annotations

from typing import Any

from austial.orm.driver.sqlalchemy_support import SchemaCatalog
from austial.orm.expression import DriverResult, SelectSpec
from austial.orm.metadata.entity_metadata import EntityMetadata, RelationType


class RowHydrator:
    def __init__(self, catalog: SchemaCatalog):
        self._catalog = catalog

    def hydrate(self, spec: SelectSpec, result: DriverResult) -> list[Any]:
        labels_by_alias = result.labels_by_alias or {}
        root_meta = self._catalog.metadata_by_entity[spec.entity]

        # alias -> (target entity class, its metadata, the relation on the root that reaches it)
        joined_by_alias: dict[str, tuple[type, EntityMetadata, Any]] = {}
        for join in spec.joins:
            if not join.select:
                continue
            _, relation_attr = join.relation_name.split(".", 1)
            rel = root_meta.relation(relation_attr)
            if rel is None:  # pragma: no cover - QueryBuilder already validates this
                continue
            target_cls = rel.target()
            joined_by_alias[join.alias] = (target_cls, self._catalog.metadata_by_entity[target_cls], rel)

        root_pk_name = self._catalog.pk_column(root_meta).column_name
        root_labels = labels_by_alias.get(spec.alias, [c.column_name for c in root_meta.columns])

        order: list[Any] = []
        groups: dict[Any, list[dict[str, Any]]] = {}
        for row in result.rows:
            pk_value = row.get(f"{spec.alias}__{root_pk_name}")
            if pk_value not in groups:
                groups[pk_value] = []
                order.append(pk_value)
            groups[pk_value].append(row)

        entities: list[Any] = []
        for pk_value in order:
            group_rows = groups[pk_value]
            instance = self._build_instance(spec.entity, root_meta, group_rows[0], spec.alias, root_labels)

            for alias, (target_cls, target_meta, rel) in joined_by_alias.items():
                target_labels = labels_by_alias.get(alias, [c.column_name for c in target_meta.columns])
                target_pk_name = self._catalog.pk_column(target_meta).column_name
                is_to_many = rel.relation_type in (RelationType.ONE_TO_MANY, RelationType.MANY_TO_MANY)

                if is_to_many:
                    seen: set[Any] = set()
                    children = []
                    for row in group_rows:
                        child_pk = row.get(f"{alias}__{target_pk_name}")
                        if child_pk is None or child_pk in seen:
                            continue
                        seen.add(child_pk)
                        children.append(self._build_instance(target_cls, target_meta, row, alias, target_labels))
                    setattr(instance, rel.attribute_name, children)
                else:
                    row = group_rows[0]
                    child_pk = row.get(f"{alias}__{target_pk_name}")
                    child = (
                        None
                        if child_pk is None
                        else self._build_instance(target_cls, target_meta, row, alias, target_labels)
                    )
                    setattr(instance, rel.attribute_name, child)

            entities.append(instance)
        return entities

    @staticmethod
    def _build_instance(
        entity_cls: type, meta: EntityMetadata, row: dict[str, Any], alias: str, column_names: list[str]
    ) -> Any:
        prefix = f"{alias}__"
        values = {name: row.get(f"{prefix}{name}") for name in column_names}
        kwargs = {col.attribute_name: values.get(col.column_name) for col in meta.columns}
        return entity_cls(**kwargs)
