"""Seed script for dental demo: download, transcribe, embed, and store videos.

Usage:
    cd implementation_layer/toolkit_demo_app
    python api/scripts/seed_dental_demo.py

Requires: yt-dlp, ffmpeg, boto3, gaik[all-cpu]>=0.3.10
Reads config from .env.local (LOCAL_WHISPER_BASE, LOCAL_WHISPER_KEY, DATABASE_URL, ALLAS_*)
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# Load env from toolkit_demo_app/.env.local
SCRIPT_DIR = Path(__file__).resolve().parent
DEMO_DIR = SCRIPT_DIR.parent.parent
load_dotenv(DEMO_DIR / ".env.local")

# ── Video list ──────────────────────────────────────────────────────────────

VIDEOS = [
    "https://www.youtube.com/watch?v=0Ijh-3oF0_U",
    "https://www.youtube.com/watch?v=StvEM_e93Tg",
    "https://www.youtube.com/watch?v=gWXXEKtgJFg",
    "https://www.youtube.com/watch?v=K6ab0uW-2ao",
    "https://www.youtube.com/watch?v=u9V9KMw98sA",
    "https://www.youtube.com/watch?v=PNo6SXuLTUY",
    "https://www.youtube.com/watch?v=Tt7BIgQCrnU",
    "https://www.youtube.com/watch?v=NhL_qUwRrhk",
    "https://www.youtube.com/watch?v=Np6u9IChEmI",
    "https://www.youtube.com/watch?v=TQvM71yv9LU",
    "https://www.youtube.com/watch?v=MRZiZ27SebI",
]

ALLAS_PREFIX = "dental-demo"


def _video_id(url: str) -> str:
    """Deterministic short ID from URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _ytdlp_cmd() -> list[str]:
    """Return yt-dlp command prefix, using python -m fallback on Windows."""
    if shutil.which("yt-dlp"):
        try:
            subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=5, check=True)
            return ["yt-dlp"]
        except (PermissionError, OSError):
            pass
    return [sys.executable, "-m", "yt_dlp"]


def download_video(url: str, out_dir: Path) -> tuple[Path, str]:
    """Download video with yt-dlp. Returns (video_path, title)."""
    ytdlp = _ytdlp_cmd()

    # First get metadata for the title
    title_cmd = [*ytdlp, "--get-title", url]
    title_result = subprocess.run(title_cmd, capture_output=True, text=True, timeout=60)
    title = title_result.stdout.strip() if title_result.returncode == 0 else "Untitled"

    video_path = out_dir / "video.mp4"
    cmd = [
        *ytdlp,
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(video_path),
        url,
    ]
    subprocess.run(cmd, check=True, timeout=600)
    return video_path, title


def extract_thumbnail(video_path: Path, out_dir: Path) -> Path:
    """Extract a thumbnail frame from the video."""
    thumb_path = out_dir / "thumbnail.jpg"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ss", "10",
        "-vframes", "1",
        "-q:v", "5",
        str(thumb_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=60)
    return thumb_path


def transcribe_video(video_path: Path) -> dict:
    """Transcribe using local Whisper."""
    from gaik.software_components.transcriber.whisper_local import transcribe

    api_base = os.getenv("LOCAL_WHISPER_BASE")
    api_key = os.getenv("LOCAL_WHISPER_KEY")
    if not api_base or not api_key:
        raise RuntimeError("LOCAL_WHISPER_BASE and LOCAL_WHISPER_KEY must be set")

    return transcribe(
        audio_path=video_path,
        api_base=api_base,
        key=api_key,
        language="auto",
    )


def upload_to_allas(local_path: Path, s3_key: str) -> None:
    """Upload a file to Allas S3."""
    import boto3
    from botocore.config import Config as BotoConfig

    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("ALLAS_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("ALLAS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("ALLAS_SECRET_ACCESS_KEY"),
        region_name="regionOne",
        config=BotoConfig(s3={"addressing_style": "path"}),
    )

    bucket = os.getenv("ALLAS_BUCKET_NAME", "toolkit-demo-app")
    s3.upload_file(str(local_path), bucket, s3_key)
    print(f"  Uploaded: s3://{bucket}/{s3_key}")


def process_video(url: str, work_dir: Path) -> dict | None:
    """Full pipeline for one video: download → transcribe → upload → embed → store."""
    vid = _video_id(url)
    video_dir = work_dir / vid
    video_dir.mkdir(exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Processing: {url}")
    print(f"Video ID: {vid}")

    # 1. Download
    print("  [1/6] Downloading video...")
    try:
        video_path, title = download_video(url, video_dir)
    except Exception as e:
        print(f"  SKIP: Download failed - {e}")
        return None

    # 2. Extract thumbnail
    print("  [2/6] Extracting thumbnail...")
    thumb_path = extract_thumbnail(video_path, video_dir)

    # 3. Transcribe
    print("  [3/6] Transcribing with local Whisper...")
    try:
        result = transcribe_video(video_path)
    except Exception as e:
        print(f"  SKIP: Transcription failed - {e}")
        return None

    segments = result.get("segments", [])
    raw_text = (result.get("text") or "").strip()
    print(f"  Got {len(segments)} segments")

    # 4. Generate SRT
    print("  [4/6] Generating SRT...")
    from gaik.software_components.transcriber.srt_utils import (
        chunk_segments,
        segments_to_srt,
    )

    srt_content = segments_to_srt(segments)
    srt_path = video_dir / "subtitles.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    # 5. Upload to Allas
    print("  [5/6] Uploading to Allas...")
    prefix = f"{ALLAS_PREFIX}/{vid}"
    try:
        upload_to_allas(video_path, f"{prefix}/video.mp4")
        upload_to_allas(srt_path, f"{prefix}/subtitles.srt")
        if thumb_path.exists():
            upload_to_allas(thumb_path, f"{prefix}/thumbnail.jpg")
    except Exception as e:
        print(f"  WARNING: Upload failed - {e}")
        print("  Continuing with embedding anyway...")

    # 6. Chunk, embed, store
    print("  [6/6] Embedding and storing segments...")
    chunks = chunk_segments(segments, target_seconds=45)

    from gaik.software_components.RAG.pg_vector_store.video_search_helpers import (
        ingest_video_segments,
    )

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("  SKIP: DATABASE_URL not set, cannot store embeddings")
        return {"video_id": vid, "title": title, "segments": len(segments)}

    from gaik.software_components.config import get_openai_config
    from gaik.software_components.RAG.embedder import Embedder
    from gaik.software_components.RAG.pg_vector_store import PgVectorStore

    use_azure = bool(os.getenv("AZURE_API_KEY"))
    config = get_openai_config(use_azure=use_azure)
    embedder = Embedder(config=config, model="text-embedding-3-small")

    with PgVectorStore(
        db_url,
        table_name="video_segments",
        embedding_dim=1536,
        fts_language="simple",
    ) as store:
        store.setup()
        ids = ingest_video_segments(
            store,
            embedder,
            video_title=title,
            video_id=vid,
            segments=chunks,
            extra_metadata={"thumbnail_key": f"{ALLAS_PREFIX}/{vid}/thumbnail.jpg"},
        )
        print(f"  Stored {len(ids)} chunks in database")

    return {"video_id": vid, "title": title, "segments": len(segments), "chunks": len(ids)}


def main():
    print("=" * 60)
    print("GAIK Dental Demo Seed Script")
    print("=" * 60)

    # Check prerequisites
    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found in PATH")
        sys.exit(1)

    # Verify yt-dlp works (handles Windows permission issues)
    try:
        ytdlp = _ytdlp_cmd()
        subprocess.run([*ytdlp, "--version"], capture_output=True, timeout=10, check=True)
        print(f"Using yt-dlp via: {' '.join(ytdlp)}")
    except Exception as e:
        print(f"ERROR: yt-dlp not available - {e}")
        sys.exit(1)

    required_envs = ["LOCAL_WHISPER_BASE", "LOCAL_WHISPER_KEY"]
    for env in required_envs:
        if not os.getenv(env):
            print(f"ERROR: {env} not set")
            sys.exit(1)

    work_dir = Path(tempfile.mkdtemp(prefix="dental_seed_"))
    print(f"Working directory: {work_dir}")
    print(f"Videos to process: {len(VIDEOS)}")

    results = []
    for url in VIDEOS:
        result = process_video(url, work_dir)
        if result:
            results.append(result)

    print(f"\n{'='*60}")
    print(f"SEED COMPLETE: {len(results)}/{len(VIDEOS)} videos processed")
    for r in results:
        print(f"  - {r['title']} ({r['video_id']}): {r.get('chunks', '?')} chunks")

    # Cleanup
    print(f"\nCleaning up {work_dir}...")
    shutil.rmtree(work_dir, ignore_errors=True)
    print("Done!")


if __name__ == "__main__":
    main()
