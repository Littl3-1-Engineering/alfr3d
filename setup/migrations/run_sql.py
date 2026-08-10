"""Helpers for running raw MySQL script files inside Alembic migrations.

The ALFR3D schema is authored as plain ``.sql`` files (see ``setup/*.sql``).
These helpers split a MySQL script into individual statements, honoring the
``DELIMITER`` directives used around triggers/events, and execute each
statement through Alembic's ``op.execute``.
"""

import os
import re

import sqlalchemy as sa

_DELIMITER_RE = re.compile(r"^\s*DELIMITER\s+(\S+)\s*$", re.IGNORECASE)

_SETUP_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def sql_path(filename):
    """Absolute path of a raw SQL file under setup/."""
    return os.path.join(_SETUP_DIR, filename)


def split_sql_script(text):
    """Split a MySQL script into statements, honoring DELIMITER directives."""
    statements = []
    current = []
    delimiter = ";"

    def flush():
        if not current:
            return
        stmt = "\n".join(current).strip().rstrip(";").strip()
        if stmt:
            statements.append(stmt)
        current.clear()

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _DELIMITER_RE.match(stripped)
        if match:
            flush()
            delimiter = match.group(1)
            continue
        if stripped.startswith("--"):
            continue
        current.append(raw_line)
        if stripped.endswith(delimiter):
            flush()
    flush()
    return statements


def run_sql_file(op, path):
    """Execute every statement in a raw SQL file via Alembic's op.execute."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    for statement in split_sql_script(text):
        op.execute(statement)


def drop_foreign_keys_for_column(op, table, column):
    """Drop FK constraints on ``table`` that reference ``column``.

    MySQL refuses to drop an index that backs a foreign key, so downgrades must
    remove the FK constraint first. Looks the names up from information_schema
    instead of hardcoding auto-generated names.
    """
    bind = op.get_bind()
    if bind is None:
        return
    rows = bind.execute(
        sa.text(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
            "AND COLUMN_NAME = :column"
        ),
        {"table": table, "column": column},
    ).fetchall()
    for (name,) in rows:
        op.execute(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{name}`;")
