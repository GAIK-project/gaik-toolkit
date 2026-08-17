"""Unit tests for the tabular_agent's second security layer.

``sql_safety`` rejects dangerous SQL before it runs; this module covers what
happens if something ever slips past it. Once the files are loaded, the DuckDB
connection is locked so that reading the filesystem, installing extensions,
attaching databases and re-enabling any of the above all fail at the engine
level, regardless of what SQL reaches it.
"""

import pytest

pytest.importorskip("duckdb")

import duckdb  # noqa: E402
from gaik.software_components.tabular_agent import TabularAgent  # noqa: E402
from gaik.software_components.tabular_agent.loader import lock_down  # noqa: E402


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text("region,units\nNorth,120\nSouth,90\n", encoding="utf-8")
    return path


@pytest.fixture
def secret_file(tmp_path):
    path = tmp_path / "secret.csv"
    path.write_text("password\nhunter2\n", encoding="utf-8")
    return path


def test_loaded_data_is_still_queryable_after_lockdown(csv_file):
    with TabularAgent(csv_file) as agent:
        assert agent.run_sql("SELECT count(*) AS n FROM sales") == [{"n": 2}]


@pytest.mark.parametrize(
    "statement",
    [
        "SET enable_external_access = true",
        "SET lock_configuration = false",
    ],
)
def test_lockdown_cannot_be_undone(csv_file, statement):
    with TabularAgent(csv_file) as agent:
        con = agent._get_conn()
        with pytest.raises(duckdb.Error):
            con.execute(statement)


def test_engine_blocks_file_reads_even_if_validation_is_bypassed(csv_file, secret_file):
    """The last line of defence: run the SQL directly against the connection."""
    with TabularAgent(csv_file) as agent:
        con = agent._get_conn()
        posix = secret_file.as_posix()
        with pytest.raises(duckdb.Error):
            con.execute(f"SELECT * FROM read_csv('{posix}')")


def test_engine_blocks_attach_and_install(csv_file, tmp_path):
    with TabularAgent(csv_file) as agent:
        con = agent._get_conn()
        for statement in (
            f"ATTACH '{(tmp_path / 'x.db').as_posix()}'",
            "INSTALL httpfs",
        ):
            with pytest.raises(duckdb.Error):
                con.execute(statement)


def test_lock_down_is_idempotent_and_standalone():
    con = duckdb.connect(":memory:")
    try:
        con.execute("CREATE TABLE t AS SELECT 1 AS a")
        lock_down(con)
        assert con.execute("SELECT a FROM t").fetchone() == (1,)
        with pytest.raises(duckdb.Error):
            con.execute("SET enable_external_access = true")
    finally:
        con.close()


# ------------------------------------------------------------ agent behaviour


def test_run_sql_rejects_unsafe_sql_before_reaching_duckdb(csv_file, secret_file):
    from gaik.software_components.tabular_agent import UnsafeSQLError

    with TabularAgent(csv_file) as agent:
        with pytest.raises(UnsafeSQLError):
            agent.run_sql(f"SELECT * FROM read_csv('{secret_file.as_posix()}')")


def test_run_sql_applies_the_row_cap(tmp_path):
    path = tmp_path / "big.csv"
    path.write_text("n\n" + "\n".join(str(i) for i in range(50)), encoding="utf-8")
    with TabularAgent(path, max_rows=10) as agent:
        assert len(agent.run_sql("SELECT n FROM big")) == 10


def test_run_sql_needs_no_llm_credentials(csv_file):
    """The tool-style methods must work with no LLM config at all."""
    with TabularAgent(csv_file, config={}) as agent:
        assert agent.table_names == ["sales"]
        assert agent.get_schema().tables[0].row_count == 2


def test_invalid_layout_inference_value_is_rejected(csv_file):
    with pytest.raises(ValueError, match="layout_inference"):
        TabularAgent(csv_file, layout_inference="sometimes")


def test_close_releases_the_connection(csv_file):
    agent = TabularAgent(csv_file)
    agent.get_schema()
    agent.close()
    assert agent._conn is None
    # Reopening loads the files again rather than failing.
    assert agent.run_sql("SELECT count(*) AS n FROM sales") == [{"n": 2}]
    agent.close()
