"""Which input kinds a case step accepts when a PoC test file is reused (#253)."""

from wizard_api.routers.cases import _is_audio_output, _reusable_poc_inputs, _task_contract_kinds
from wizard_api.services import input_content


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
    assert _task_contract_kinds(process, "T_doc", frozenset({"wav"})) == frozenset()
    # Unknown task or no process: the contract as it is.
    assert _task_contract_kinds(process, "T_missing", mixed) == mixed
    assert _task_contract_kinds(None, "T_audio", mixed) == mixed


def test_reusable_inputs_recheck_changed_files_and_contracts(tmp_path, monkeypatch):
    sample_dir = tmp_path / "sample_input"
    sample_dir.mkdir()
    path = sample_dir / "report.txt"
    path.write_text("Fault report", encoding="utf-8")
    checked = []
    original_check = input_content.check

    def record_check(name, data, kinds):
        checked.append((name, kinds))
        return original_check(name, data, kinds)

    monkeypatch.setattr(input_content, "check", record_check)
    text_contract = {"technical_spec": {"input_types": ["txt"]}}
    audio_contract = {"technical_spec": {"input_types": ["audio"]}}

    expected = [{"name": "report.txt", "bytes": 12, "uploaded": False}]
    assert _reusable_poc_inputs(str(tmp_path), text_contract, []) == expected
    assert _reusable_poc_inputs(str(tmp_path), text_contract, []) == expected
    assert checked == [("report.txt", frozenset({"txt"}))]
    assert _reusable_poc_inputs(str(tmp_path), audio_contract, []) == []

    path.write_bytes(b"\x00\x00")
    assert _reusable_poc_inputs(str(tmp_path), text_contract, []) == []
    assert len(checked) == 3
