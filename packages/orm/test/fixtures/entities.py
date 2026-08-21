"""Reusable fixture entities for ``austial-orm``'s test suite -- imported (never redefined) by
every spec module, so ``MetadataRegistry`` only ever sees one registration per entity class.

``Owner``/``Cat`` form a ``OneToMany``/``ManyToOne`` pair; ``Cat``/``Toy`` form a ``ManyToMany``
pair (owned by ``Cat.toys``, which carries the join table). ``Owner`` intentionally declares its
``cats`` relation (a forward reference to ``Cat``, which is defined *after* it in this module) --
this is the exact ordering the framework's own docs use, and is a deliberate regression fixture
for ``@Entity()``'s per-attribute (not all-at-once) annotation resolution.
"""

from __future__ import annotations

import datetime

from austial.orm import (
    Column,
    CreateDateColumn,
    Entity,
    JoinColumn,
    JoinTable,
    ManyToMany,
    ManyToOne,
    OneToMany,
    PrimaryGeneratedColumn,
)


@Entity()
class Owner:
    id: int = PrimaryGeneratedColumn()
    name: str = Column()
    cats: list[Cat] = OneToMany(lambda: Cat, inverse_side="owner")


@Entity()
class Toy:
    id: int = PrimaryGeneratedColumn()
    name: str = Column()
    cats: list[Cat] = ManyToMany(lambda: Cat, inverse_side="toys")


@Entity()
class Cat:
    id: int = PrimaryGeneratedColumn()
    name: str = Column()
    age: int = Column(nullable=True)
    created_at: datetime.datetime = CreateDateColumn()
    owner: Owner = ManyToOne(lambda: Owner, "cats", join_column=JoinColumn(name="owner_id"))
    toys: list[Toy] = ManyToMany(lambda: Toy, "cats", join_table=JoinTable())


@Entity()
class Order:
    """Deliberately named after a SQL reserved keyword (both Postgres and SQLite reserve
    ``ORDER``) -- regression fixture for the ``EntityManager``-internal WHERE/ORDER BY
    fragment builders correctly quoting the identifiers they splice together (table name doubles
    as the query alias -- see ``EntityManager._alias_for`` -- and ``group`` is *also* reserved, so
    this one entity exercises both a reserved table/alias name and a reserved column name at
    once)."""

    id: int = PrimaryGeneratedColumn()
    group: str = Column()
    total: int = Column(nullable=True)


@Entity(append_only=True)
class LedgerEntry:
    """Regression fixture for ``@Entity(append_only=True)`` -- stands in for the real
    ``LedgerEntry``/``AuditLog`` entities the build plan ships later (append-only ledger rows,
    7-year-retention audit rows): INSERT must still work, every UPDATE/remove/delete path must
    raise ``AppendOnlyViolationError`` at the ``EntityManager`` choke point."""

    id: int = PrimaryGeneratedColumn()
    description: str = Column()
    amount: int = Column(nullable=True)
