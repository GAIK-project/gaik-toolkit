"""Which input kinds a case step accepts when a PoC test file is reused (#253)."""

from wizard_api.routers.cases import _is_audio_output, _task_contract_kinds


def test_is_audio_output_matches_audio_words_but_not_lookalikes():
    assert _is_audio_output("Call recording")
    assert _is_audio_output("customerVoice")
    assert _is_audio_output("Puheäänite")
    assert not _is_audio_output("Invoice PDF")
    assert not _is_audio_output("Puhelinnumero")
    assert not _is_audio_output(None)


def test_task_contract_kinds_narrows_per_step_and_never_widens_the_contract():
    process = {
        "nodes": [
            {"id": "T_audio", "kind": "userTask", "outputs": ["Call recording"]},
            {"id": "T_doc", "kind": "userTask", "outputs": ["Invoice PDF"]},
        ]
    }
    mixed = frozenset({"wav", "mp3", "pdf", "docx"})
    assert _task_contract_kinds(process, "T_audio", mixed) == frozenset({"wav", "mp3"})
    assert _task_contract_kinds(process, "T_doc", mixed) == frozenset({"pdf", "docx"})
    # A documents-only contract: an audio step gets nothing, not audio.
    assert _task_contract_kinds(process, "T_audio", frozenset({"pdf"})) == frozenset()
    # Unknown task or no process: the contract as it is.
    assert _task_contract_kinds(process, "T_missing", mixed) == mixed
    assert _task_contract_kinds(None, "T_audio", mixed) == mixed
