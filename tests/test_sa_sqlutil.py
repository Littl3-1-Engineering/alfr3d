"""sql_str: paths and values spliced into DuckDB statements can never break out of the literal."""

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from sa.sqlutil import sql_str


def test_plain_value_is_quoted():
    assert sql_str("a/b.parquet") == "'a/b.parquet'"


def test_embedded_quotes_are_doubled():
    assert sql_str("it's") == "'it''s'"


def test_nul_byte_is_rejected():
    with pytest.raises(ValueError):
        sql_str("a\x00b")


def test_a_path_with_a_quote_and_injection_attempt_is_read_as_one_filename(tmp_path):
    evil = tmp_path / "x'); DROP TABLE t; --.parquet"
    pq.write_table(pa.table({"v": [1, 2, 3]}), evil)
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT 42 AS keep")
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet({sql_str(evil)})").fetchall()[0][0]
    assert n == 3
    assert con.execute("SELECT keep FROM t").fetchall() == [(42,)]


def test_a_view_over_such_a_path_works(tmp_path):
    evil = tmp_path / "it's.parquet"
    pq.write_table(pa.table({"v": [1]}), evil)
    con = duckdb.connect()
    con.execute(f"CREATE VIEW v AS SELECT * FROM read_parquet({sql_str(evil)})")
    assert con.execute("SELECT v FROM v").fetchall() == [(1,)]
