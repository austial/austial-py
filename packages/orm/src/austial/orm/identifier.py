"""ANSI SQL identifier quoting -- wraps the table/column identifiers ``EntityManager`` splices
into the raw-SQL ``WhereFragment``/``OrderBySpec`` text it builds *on the caller's behalf* (from
``FindOptions.where``, bulk-``update()``/``delete()`` criteria, PK lookups, ``order_by`` tuples --
see ``entity_manager.py``), so table/column names that collide with a SQL reserved word (``user``,
``order``, ``group``, ``check``, ...) don't produce a syntax error the way an unquoted
``WHERE user.email = :p0`` does against Postgres (``USER`` is a reserved keyword there).

Double-quoted identifiers are the ANSI-SQL standard, understood identically by every driver this
package ships (Postgres, SQLite) -- so quoting is applied unconditionally here rather than only
when a name is actually a reserved word in some specific dialect, which is the same defensive
posture SQLAlchemy's own ``Table``/``Column`` compilation already gives the `SELECT`/`FROM` clauses
built via ``Table.alias().c[...]`` in ``driver/sqlalchemy_support.py``'s ``compile_select`` --
those are compiled objects, not hand-formatted text, so they're already quoted correctly; this
module brings the hand-formatted WHERE/ORDER BY text fragments up to the same guarantee.

Deliberately *not* applied to ``QueryBuilder.where()``/``.and_where()``/``.or_where()``/
``.order_by()``/``.add_order_by()`` themselves when called directly by application code -- those
are documented raw-SQL escape hatches (same contract as TypeORM's own querybuilder), so quoting
reserved words there is the caller's responsibility, same as writing any other raw SQL.
"""

from __future__ import annotations


def quote_identifier(name: str) -> str:
    """Wraps a single identifier in ANSI double-quotes, escaping any literal ``"`` by doubling it
    (the standard SQL escape for a quoted identifier)."""
    return '"' + name.replace('"', '""') + '"'


def quote_ref(alias: str, column: str) -> str:
    """``"alias"."column"`` -- the qualified-reference shape every WHERE/ORDER BY fragment
    ``EntityManager`` builds needs."""
    return f"{quote_identifier(alias)}.{quote_identifier(column)}"
