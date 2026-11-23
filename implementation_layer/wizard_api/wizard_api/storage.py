"""Session artefact directory helpers (S1-5)."""

from pathlib import Path


def ensure_output_dir(output_dir: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
