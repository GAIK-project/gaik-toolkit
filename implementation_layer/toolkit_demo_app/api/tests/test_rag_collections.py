"""RAG collections: ids nobody can guess, no chunk listing, eviction, and a scoped clear."""

from __future__ import annotations

import asyncio
import inspect
import io
from types import SimpleNamespace

import pytest
from api.routers import rag
from api.utils.result_owner import USER_HEADER, owned_by, remember_owner
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from langchain_core.documents import Document


@pytest.fixture(autouse=True)
def empty_store(monkeypatch) -> None:
    monkeypatch.setattr(rag, "RAG_INSTANCES", {})
    monkeypatch.setattr(rag, "_USAGE", {})
    monkeypatch.setattr(rag, "_collection_locks", {})
    from api.utils import result_owner

    monkeypatch.setattr(result_owner, "_owners", {})


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(rag.router, prefix="/rag")
    return TestClient(app)


def _add(
    collection_id: str, *, last_used: float = 0.0, in_flight: int = 0, owner: str = ""
) -> None:
    """A collection; by default owned by "", the user of a test client that sends none."""
    rag.RAG_INSTANCES[collection_id] = SimpleNamespace()
    rag._USAGE[collection_id] = [last_used, in_flight]
    remember_owner(collection_id, owner)


def _index(monkeypatch, collection_id: str | None, user: str = "u1"):
    workflow = SimpleNamespace(api_config={}, index_chunk_documents=len)
    monkeypatch.setattr(rag, "get_rag_api_config", lambda: {})
    monkeypatch.setattr(rag, "_build_demo_workflow", lambda config, cid: workflow)
    monkeypatch.setattr(
        rag,
        "_parse_document_to_chunks",
        lambda path, **kwargs: ([Document(page_content="text", metadata={})], "pymupdf"),
    )
    pdf = (rag.EXAMPLE_DIR / rag.EXAMPLE_DOCUMENTS[0]["filename"]).read_bytes()
    return asyncio.run(
        rag.index_documents(
            files=[UploadFile(io.BytesIO(pdf), filename="a.pdf")],
            collection_id=collection_id,
            parser_choice="pymupdf",
            user=user,
        )
    )


def test_a_new_collection_gets_a_full_random_id(monkeypatch) -> None:
    first = _index(monkeypatch, None).collection_id
    second = _index(monkeypatch, None).collection_id

    assert first != second
    for collection_id in (first, second):
        assert len(collection_id) == 32
        int(collection_id, 16)  # 128 random bits as hex


def test_an_id_the_server_does_not_know_is_not_adopted(monkeypatch) -> None:
    response = _index(monkeypatch, "guess-me")

    assert response.collection_id != "guess-me"
    assert "guess-me" not in rag.RAG_INSTANCES
    assert "guess-me" not in rag._collection_locks


def test_indexing_adds_to_the_callers_existing_collection(monkeypatch) -> None:
    first = _index(monkeypatch, None).collection_id

    assert _index(monkeypatch, first).collection_id == first
    assert list(rag.RAG_INSTANCES) == [first]


def test_no_route_lists_the_chunks_of_a_collection(client) -> None:
    _add("c1")

    assert client.get("/rag/debug/c1").status_code == 404
    assert not [route.path for route in rag.router.routes if "debug" in route.path]


def test_search_type_is_no_longer_a_parameter() -> None:
    for handler in (rag.query_rag, rag.query_rag_stream):
        assert "search_type" not in inspect.signature(handler).parameters


def test_idle_collections_are_evicted_and_used_ones_stay() -> None:
    now = 10_000.0
    _add("idle", last_used=now - rag.COLLECTION_IDLE_SECONDS - 1)
    _add("recent", last_used=now - 60)
    _add("querying", last_used=now - rag.COLLECTION_IDLE_SECONDS - 1, in_flight=1)

    assert rag.evict_collections(now) == 1

    assert set(rag.RAG_INSTANCES) == {"recent", "querying"}
    assert "idle" not in rag._USAGE


def test_a_collection_being_indexed_is_not_evicted() -> None:
    async def run() -> None:
        _add("indexing", last_used=0.0)
        lock = await rag._get_collection_lock("indexing")
        async with lock:
            assert rag.evict_collections(10**9) == 0
        assert rag.evict_collections(10**9) == 1

    asyncio.run(run())


def test_a_query_marks_the_collection_as_used() -> None:
    _add("c1", last_used=0.0)

    with rag._in_use("c1"):
        assert rag._is_busy("c1")

    assert not rag._is_busy("c1")
    assert rag.evict_collections() == 0  # just used


def test_the_cap_evicts_the_least_recently_used(monkeypatch) -> None:
    monkeypatch.setattr(rag, "MAX_COLLECTIONS", 3)
    now = 10_000.0
    _add("oldest", last_used=now - 300)
    _add("older", last_used=now - 200)
    _add("newest", last_used=now - 100)

    rag.evict_collections(now, make_room=True)

    assert set(rag.RAG_INSTANCES) == {"older", "newest"}


def test_indexing_is_refused_when_every_collection_is_in_use(monkeypatch) -> None:
    monkeypatch.setattr(rag, "MAX_COLLECTIONS", 2)
    _add("a", in_flight=1)
    _add("b", in_flight=1)

    with pytest.raises(rag.HTTPException) as refused:
        _index(monkeypatch, None)

    assert refused.value.status_code == 503
    assert set(rag.RAG_INSTANCES) == {"a", "b"}


def test_the_sweep_runs_without_any_request(monkeypatch) -> None:
    _add("idle", last_used=-rag.COLLECTION_IDLE_SECONDS - 1)
    monkeypatch.setattr(rag.time, "monotonic", lambda: 0.0)
    sleeps = 0

    async def sleep(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(rag.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(rag.cleanup_idle_collections())

    assert rag.RAG_INSTANCES == {}


def test_the_api_starts_the_collection_and_session_sweeps(monkeypatch) -> None:
    from api import main

    started = []

    async def rag_sweep() -> None:
        started.append("rag")

    async def tabular_sweep() -> None:
        started.append("tabular")

    monkeypatch.setattr(main.rag, "cleanup_idle_collections", rag_sweep)
    monkeypatch.setattr(main.tabular_agent, "cleanup_idle_sessions", tabular_sweep)
    with TestClient(main.app):
        pass

    assert sorted(started) == ["rag", "tabular"]


def test_clear_removes_only_the_collections_the_caller_names(client) -> None:
    _add("mine")
    _add("also-mine")
    _add("someone-elses", owner="other")

    response = client.delete(
        "/rag/clear", params={"collection_ids": ["mine", "also-mine", "unknown"]}
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Cleared 2 collections"
    assert list(rag.RAG_INSTANCES) == ["someone-elses"]


def test_clear_without_ids_clears_nothing(client) -> None:
    _add("someone-elses", owner="other")

    assert client.delete("/rag/clear").status_code == 422
    assert list(rag.RAG_INSTANCES) == ["someone-elses"]


def test_the_shared_example_is_not_cleared_by_one_visitor(client) -> None:
    example = f"{rag.EXAMPLE_COLLECTION_PREFIX}-pymupdf"
    _add(example)
    _add("mine")

    assert client.delete(f"/rag/clear/{example}").status_code == 200
    assert client.delete("/rag/clear/mine").status_code == 200
    client.delete("/rag/clear", params={"collection_ids": [example]})

    assert list(rag.RAG_INSTANCES) == [example]


def test_a_new_collection_belongs_to_the_user_who_indexed_it(monkeypatch) -> None:
    collection = _index(monkeypatch, None, user="u1").collection_id

    assert owned_by(collection, "u1") and not owned_by(collection, "u2")


def test_indexing_into_another_users_collection_starts_a_new_one(monkeypatch) -> None:
    theirs = _index(monkeypatch, None, user="u1").collection_id

    mine = _index(monkeypatch, theirs, user="u2").collection_id

    assert mine != theirs and owned_by(mine, "u2")


def test_another_user_cannot_query_see_or_clear_a_collection(client) -> None:
    _add("theirs", owner="u1")
    rag.RAG_INSTANCES["theirs"] = SimpleNamespace(vector_store=SimpleNamespace(count=lambda: 2))
    other = {USER_HEADER: "u2"}

    queried = client.post(
        "/rag/query", data={"question": "What?", "collection_id": "theirs"}, headers=other
    )
    streamed = client.post(
        "/rag/query/stream", data={"question": "What?", "collection_id": "theirs"}, headers=other
    )
    status = client.get("/rag/status/theirs", headers=other).json()
    client.delete("/rag/clear/theirs", headers=other)
    client.delete("/rag/clear", params={"collection_ids": ["theirs"]}, headers=other)

    assert queried.status_code == 404 and streamed.status_code == 404
    assert status["collection_id"] is None and status["is_ready"] is False
    assert "theirs" in rag.RAG_INSTANCES and owned_by("theirs", "u1")  # kept for its owner
    owner_status = client.get("/rag/status/theirs", headers={USER_HEADER: "u1"}).json()
    assert owner_status["collection_id"] == "theirs" and owner_status["is_ready"] is True


def test_the_shared_example_answers_every_visitor(client) -> None:
    example = f"{rag.EXAMPLE_COLLECTION_PREFIX}-pymupdf"
    rag.RAG_INSTANCES[example] = SimpleNamespace(vector_store=SimpleNamespace(count=lambda: 3))
    rag._USAGE[example] = [0.0, 0]

    status = client.get(f"/rag/status/{example}", headers={USER_HEADER: "anyone"}).json()

    assert status["collection_id"] == example and status["is_ready"] is True


def test_clearing_a_collection_forgets_its_owner(client) -> None:
    _add("mine", owner="u1")

    client.delete("/rag/clear/mine", headers={USER_HEADER: "u1"})

    assert "mine" not in rag.RAG_INSTANCES and not owned_by("mine", "u1")


def test_a_collection_dropped_while_an_upload_waits_comes_back_for_its_user(monkeypatch) -> None:
    mine = _index(monkeypatch, None, user="u1").collection_id
    real_lock = rag._get_collection_lock

    async def lock_after_a_clear(collection_id):
        rag._drop_collection(collection_id)  # a Clear lands while this upload waits
        return await real_lock(collection_id)

    monkeypatch.setattr(rag, "_get_collection_lock", lock_after_a_clear)

    again = _index(monkeypatch, mine, user="u1").collection_id

    assert again == mine and mine in rag.RAG_INSTANCES and owned_by(mine, "u1")


def test_a_collection_in_use_keeps_its_owner_past_the_expiry(monkeypatch, client) -> None:
    from api.utils import result_owner

    _add("mine", owner="u1")
    start = 1_000_000.0
    monkeypatch.setattr(result_owner.time, "time", lambda: start)
    result_owner.remember_owner("mine", "u1")
    later = start + result_owner.TTL_SECONDS - 60
    monkeypatch.setattr(result_owner.time, "time", lambda: later)
    assert rag._reachable("mine", "u1")  # used: the expiry starts again
    monkeypatch.setattr(result_owner.time, "time", lambda: later + 120)
    result_owner.remember_owner("other-job", "u2")  # any run prunes old entries

    assert owned_by("mine", "u1")
