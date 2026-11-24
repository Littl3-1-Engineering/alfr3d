"""Safe SQL string literals for DuckDB statements that cannot take bound parameters.

DuckDB cannot bind a parameter into DDL (``CREATE VIEW ... AS SELECT * FROM read_parquet(...)``) or
into some table-function arguments, so file paths and similar values end up inside the statement
text. Every such value goes through :func:`sql_str`, which produces a correctly escaped string
literal, so a path containing a quote (or anything else) can never terminate the literal and inject
SQL. Plain DML that can bind a parameter should still use ``?`` placeholders instead.
"""


def sql_str(value) -> str:
    """Return ``value`` as a single-quoted DuckDB string literal (embedded quotes doubled)."""
    text = str(value)
    if "\x00" in text:
        raise ValueError("NUL byte in SQL string literal")
    return "'" + text.replace("'", "''") + "'"
