"""Verify the deployed video-search demo against Allas and live endpoints.

Usage:
    cd implementation_layer/toolkit_demo_app
    uv run python api/scripts/verify_video_search_deployment.py

Reads Allas credentials from .env.local unless already present in env.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import boto3
from botocore.config import Config as BotoConfig
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
DEMO_DIR = SCRIPT_DIR.parent.parent
load_dotenv(DEMO_DIR / ".env.local")

BASE_URL = os.getenv("VIDEO_SEARCH_BASE_URL", "https://gaik-demo.2.rahtiapp.fi")
EXPECTED_FILES = {"video.mp4", "thumbnail.jpg", "subtitles.srt"}


def fetch_json(path: str) -> object:
    url = f"{BASE_URL}{path}"
    request = Request(url, headers={"User-Agent": "gaik-video-search-verify"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("ALLAS_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("ALLAS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("ALLAS_SECRET_ACCESS_KEY"),
        region_name="regionOne",
        config=BotoConfig(
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def list_bucket_files() -> dict[str, set[str]]:
    s3 = build_s3_client()
    bucket = os.getenv("ALLAS_BUCKET_NAME")
    paginator = s3.get_paginator("list_objects_v2")
    by_video: dict[str, set[str]] = defaultdict(set)

    for page in paginator.paginate(Bucket=bucket, Prefix="dental-demo/"):
        for item in page.get("Contents", []):
            parts = item["Key"].split("/")
            if len(parts) >= 3:
                by_video[parts[1]].add(parts[2])

    return by_video


def probe_media(video_id: str, kind: str) -> tuple[bool, str]:
    path = f"/api/video-search/videos/{quote(video_id)}/{kind}"
    url = f"{BASE_URL}{path}"
    request = Request(url, headers={"User-Agent": "gaik-video-search-verify"})

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return True, payload.get("url", "")
    except HTTPError as exc:
        return False, f"{exc.code} {exc.reason}"
    except URLError as exc:
        return False, str(exc.reason)


def main() -> int:
    try:
        status = fetch_json("/api/video-search/status")
        videos = fetch_json("/api/video-search/videos")
    except Exception as exc:
        print(f"ERROR: Failed to reach live deployment: {exc}")
        return 1

    if not isinstance(status, dict) or not isinstance(videos, list):
        print("ERROR: Unexpected response shape from live deployment")
        return 1

    bucket_files = list_bucket_files()
    video_ids = [video["video_id"] for video in videos if isinstance(video, dict)]

    missing_in_bucket = [video_id for video_id in video_ids if video_id not in bucket_files]
    incomplete_in_bucket = [
        video_id
        for video_id in video_ids
        if video_id in bucket_files and bucket_files[video_id] != EXPECTED_FILES
    ]

    print("Live status:", status)
    print(f"Live videos: {len(video_ids)}")
    print(f"Allas prefixes: {len(bucket_files)}")

    if video_ids:
        thumb_ok, thumb_result = probe_media(video_ids[0], "thumbnail")
        play_ok, play_result = probe_media(video_ids[0], "play")
        print(f"Sample thumbnail probe: {'OK' if thumb_ok else 'FAIL'} {thumb_result}")
        print(f"Sample playback probe: {'OK' if play_ok else 'FAIL'} {play_result}")
    else:
        thumb_ok = False
        play_ok = False

    if missing_in_bucket:
        print("Missing Allas prefixes:", ", ".join(missing_in_bucket))
    if incomplete_in_bucket:
        print("Incomplete Allas prefixes:", ", ".join(incomplete_in_bucket))

    if (
        not status.get("database_connected")
        or status.get("total_videos", 0) == 0
        or not video_ids
        or missing_in_bucket
        or incomplete_in_bucket
        or not thumb_ok
        or not play_ok
    ):
        return 1

    print("Verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
