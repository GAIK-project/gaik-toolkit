"""Generated downloads carry machine-readable AI-generated marks."""

import struct

from api.utils import ai_marking
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ai_marking.AIMarkMiddleware)

    @app.get("/pipeline/pdf/{job_id}")
    def pdf(job_id: str):
        return Response(b"%PDF-1.7", media_type="application/pdf")

    @app.get("/pipeline/pdf-missing/{job_id}")
    def other(job_id: str):
        return Response(b"x")

    @app.get("/diary/pdf/{job_id}")
    def missing(job_id: str):
        return Response(status_code=404)

    return app


def test_a_generated_download_carries_the_headers():
    response = TestClient(_app()).get("/pipeline/pdf/abc")
    assert response.headers["x-ai-generated"] == "true"
    assert response.headers["x-ai-generator"] == ai_marking.GENERATOR


def test_other_routes_and_errors_carry_none():
    client = TestClient(_app())
    assert "x-ai-generated" not in client.get("/pipeline/pdf-missing/abc").headers
    assert "x-ai-generated" not in client.get("/diary/pdf/abc").headers


def test_the_marked_routes():
    marked = [
        "/pipeline/pdf/j1",
        "/diary/pdf/j1",
        "/luvata-order/pdf/j1",
        "/dental-transcribe/srt/j1",
        "/dental-transcribe/vtt/j1",
        "/wizard/download/s1",
        "/text-to-speech",
    ]
    assert all(ai_marking.is_generated_download(p) for p in marked)
    unmarked = ["/report-writer/example/file/a.md", "/pipeline/audio", "/text-to-speech/x"]
    assert not any(ai_marking.is_generated_download(p) for p in unmarked)


def test_mp3_gets_an_id3_tag_in_front_of_the_audio():
    audio = b"\xff\xfb\x90\x00" * 4
    marked = ai_marking.mark_mp3(audio)
    assert marked.startswith(b"ID3\x03\x00")
    size = sum((b & 0x7F) << s for b, s in zip(marked[6:10], (21, 14, 7, 0), strict=True))
    tag = marked[10 : 10 + size]
    assert b"AI_GENERATED\x00true" in tag
    assert b"trainedAlgorithmicMedia" in tag
    assert marked[10 + size :] == audio


def test_wav_gets_an_info_chunk_and_a_right_riff_size():
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
    data = b"data" + struct.pack("<I", 3) + b"\x80\x80\x80"
    wav = b"RIFF" + struct.pack("<I", 4 + len(fmt) + len(data)) + b"WAVE" + fmt + data

    marked = ai_marking.mark_wav(wav)

    assert struct.unpack("<I", marked[4:8])[0] == len(marked) - 8
    assert marked[8 : len(wav)] == wav[8:]
    assert b"LIST" in marked and b"ICMT" in marked
    assert ai_marking.GENERATOR.encode() in marked


def test_other_formats_pass_unchanged():
    assert ai_marking.mark_audio(b"OggS...", "opus") == b"OggS..."
    assert ai_marking.mark_wav(b"not a wav") == b"not a wav"


def test_a_generated_pdf_names_itself_ai_generated(tmp_path):
    from api.utils.pdf_generator import StructuredDataToPDF

    out = tmp_path / "r.pdf"
    StructuredDataToPDF(title="Report").run({"total": 1}, out)
    head = out.read_bytes()
    assert b"ai_generated" in head
    assert ai_marking.GENERATOR.encode() in head
