import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from collection_sink.otlp import Retention
from collection_sink.pseudonym import PseudonymError, pseudonymise_payload
from collection_sink.server import make_handler


def s(key, value):
    return {"key": key, "value": {"stringValue": value}}


def payload(*ids):
    records = [{"attributes": [s("gaik.event.class", "audit"), s("event.name", "auth.login"), s("enduser.id", i)]}
               for i in ids]
    return {"resourceLogs": [{"resource": {"attributes": [s("service.name", "t")]},
                              "scopeLogs": [{"logRecords": records}]}]}


def fake_hmac(calls):
    def hmac(values):
        calls.append(list(values))
        return [f"vault:v1:{v[::-1]}" for v in values]
    return hmac


def attrs(p):
    return [{a["key"]: a["value"]["stringValue"] for a in r["attributes"]}
            for r in p["resourceLogs"][0]["scopeLogs"][0]["logRecords"]]


def test_raw_ids_replaced_in_one_batch_call():
    calls = []
    p = payload("a@example.com", "b@example.com", "a@example.com")
    pseudonymise_payload(p, fake_hmac(calls))
    assert calls == [["a@example.com", "b@example.com"]]
    got = attrs(p)
    assert all("enduser.id" not in a for a in got)
    assert [a["enduser.pseudo.id"] for a in got] == ["vault:v1:moc.elpmaxe@a", "vault:v1:moc.elpmaxe@b",
                                                     "vault:v1:moc.elpmaxe@a"]


def test_no_ids_no_call():
    calls = []
    p = {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"attributes": [s("event.name", "x")]}]}]}]}
    pseudonymise_payload(p, fake_hmac(calls))
    assert calls == []


class RecordingStore:
    def __init__(self):
        self.batches = []

    def write(self, batch):
        self.batches.append(batch)

    def ping(self):
        pass


@pytest.fixture
def server():
    started = []

    def start(pseudonymiser):
        store = RecordingStore()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, Retention(365, 30), pseudonymiser))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return f"http://127.0.0.1:{srv.server_port}/v1/logs", store

    yield start
    for srv in started:
        srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_vault_failure_is_503_and_nothing_stored(server):
    def broken(values):
        raise PseudonymError("vault down")

    url, store = server(broken)
    assert post(url, payload("a@example.com")) == 503
    assert store.batches == []


def test_transit_mode_stores_only_pseudonym(server):
    url, store = server(fake_hmac([]))
    assert post(url, payload("a@example.com")) == 200
    row = store.batches[0].audit[0]
    assert row.actor_pseudo_id == "vault:v1:moc.elpmaxe@a"
    assert "enduser.id" not in row.attributes
