"""PgVectorStore checks the settings it writes into SQL when it is created."""

import pytest
from gaik.software_components.RAG.pg_vector_store import PgVectorStore


@pytest.mark.parametrize(
    "language", ["simple", "finnish", "english", "pg_catalog.finnish", "my_fi"]
)
def test_a_text_search_configuration_name_is_accepted(language):
    store = PgVectorStore("postgresql://unused", fts_language=language)
    assert store.fts_language == language


@pytest.mark.parametrize(
    "language",
    ["finnish'", "fin nish", "a.b.c", "", "finnish;", "1simple", "simple--", None, 3],
)
def test_anything_else_is_refused_before_any_sql(language):
    with pytest.raises(ValueError, match="Invalid fts_language"):
        PgVectorStore("postgresql://unused", fts_language=language)


@pytest.mark.parametrize("value", [None, 40, 200])
def test_an_integer_ef_search_is_accepted(value):
    assert PgVectorStore("postgresql://unused", hnsw_ef_search=value).hnsw_ef_search == value


@pytest.mark.parametrize("value", ["100", "100; RESET ALL", 1.5, True])
def test_a_non_integer_ef_search_is_refused(value):
    with pytest.raises(ValueError, match="Invalid hnsw_ef_search"):
        PgVectorStore("postgresql://unused", hnsw_ef_search=value)
