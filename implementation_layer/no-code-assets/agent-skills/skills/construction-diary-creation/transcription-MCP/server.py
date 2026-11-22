"""MCP server for the GAIK Transcriber.

It transcribes audio and video files only, and only inside the folders the user
approved:

- every folder given with ``--folder PATH`` in the server's arguments (setup.bat
  writes the one you chose into the Claude Desktop configuration);
- every folder in the ``GAIK_TRANSCRIBE_FOLDERS`` environment variable, separated
  by ``;`` on Windows and ``:`` elsewhere;
- only when neither names a folder: the folder the server starts in.

A drive root or the home folder as a whole is never approved, nor a path relative to
a drive's current folder such as ``C:`` or ``C:recordings``. A file outside these
folders, with another extension or with content that is not audio or video, is
refused before anything is sent to the provider.

Credentials come from environment variables (``OPENAI_API_KEY``, or ``AZURE_API_KEY``
with ``AZURE_ENDPOINT`` and ``AZURE_TRANSCRIPTION_MODEL``). ``OPENAI_API_TYPE``
(``openai`` or ``azure``, which setup.bat writes into the Claude Desktop configuration)
names the provider; without it, Azure is used when only an Azure key is set. On Windows a value that
is missing from the server's environment is read from the user's environment
variables, where setup.bat saves the key. A ``.env`` file beside this script, which
older setups wrote, is read only when no key is found that way, with a warning.

``python server.py --check-folder PATH`` prints the folder as the server would approve
it (absolute) and exits 1 when it would not, or when it overlaps this kit's own folder
(holds it or lies inside it); setup.bat uses it.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("gaik-transcriber")

FOLDERS_ENV = "GAIK_TRANSCRIBE_FOLDERS"
SETTING_NAMES = (
    "OPENAI_API_KEY",
    "OPENAI_API_TYPE",
    "OPENAI_TRANSCRIPTION_MODEL",
    "AZURE_API_KEY",
    "AZURE_ENDPOINT",
    "AZURE_API_VERSION",
    "AZURE_TRANSCRIPTION_MODEL",
    "AZURE_DEPLOYMENT",
)

#: The extensions the transcriber takes: audio, and video it extracts the audio from.
MEDIA_SUFFIXES = frozenset(
    {
        ".aac",
        ".amr",
        ".flac",
        ".m4a",
        ".mp3",
        ".mpga",
        ".oga",
        ".ogg",
        ".opus",
        ".wav",
        ".wma",
        ".avi",
        ".flv",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".webm",
        ".wmv",
    }
)

# Folders approved when the server starts; see approved_folders().
APPROVED: list[Path] = []

# Initialize MCP server
mcp = FastMCP("gaik-transcriber")


class FileRefusedError(ValueError):
    """A file the server does not send to the provider; the message says why."""


def _user_environment_value(name: str) -> str:
    """A user environment variable as Windows stores it (``setx`` writes it there).

    Claude Desktop starts an MCP server with only a few environment variables, so a
    key saved as a user environment variable does not reach the process on its own.
    """
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value).strip()


def load_settings() -> None:
    """Fill missing provider settings from the user's environment, then a legacy .env.

    The .env file is read only when no key is set otherwise, so settings an older setup
    left there never mix with the key the user saved since.
    """
    for name in SETTING_NAMES:
        if not os.environ.get(name, "").strip():
            value = _user_environment_value(name)
            if value:
                os.environ[name] = value
    legacy = Path(__file__).with_name(".env")
    has_key = any(os.environ.get(name, "").strip() for name in ("OPENAI_API_KEY", "AZURE_API_KEY"))
    if legacy.is_file() and not has_key:
        logger.warning(
            "Reading provider settings from %s. Keep the key in an environment variable "
            "instead (run setup.bat again) and delete this file.",
            legacy,
        )
        load_dotenv(legacy, override=False)


def _api_config() -> dict:
    """OpenAI or Azure OpenAI settings from the environment."""
    from gaik.software_components.transcriber import get_openai_config

    api_type = os.getenv("OPENAI_API_TYPE", "").strip().lower()
    # The provider named in OPENAI_API_TYPE wins; only without it does the key decide.
    use_azure = api_type == "azure" or (
        api_type != "openai"
        and not os.getenv("OPENAI_API_KEY")
        and bool(os.getenv("AZURE_API_KEY"))
    )
    config = get_openai_config(use_azure=use_azure)
    if use_azure and not os.getenv("AZURE_TRANSCRIPTION_MODEL") and os.getenv("AZURE_DEPLOYMENT"):
        # Older setups saved the transcription deployment as AZURE_DEPLOYMENT.
        config["transcription_model"] = os.environ["AZURE_DEPLOYMENT"]
    return config


def _local_path(file_path: str) -> Path:
    """Turn a WSL-style path (/mnt/c/...) into the Windows path the server can open."""
    path = file_path.strip().strip('"')
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", path)
    if match and os.name == "nt":
        drive, rest = match.groups()
        return Path(f"{drive.upper()}:/{rest}")
    return Path(path)


def _too_broad(folder: Path) -> bool:
    """A drive root, the home folder or a folder above it: never approved as a whole."""
    home = Path.home().resolve()
    return folder == Path(folder.anchor) or folder == home or folder in home.parents


def approved_folders(
    folders: list[str], env_value: str | None = None, start: Path | None = None
) -> list[Path]:
    """The folders the server transcribes in: --folder and the env list, else the start folder.

    The start folder is approved only when no folder is named at all; when named folders
    are all refused, nothing is approved.
    """
    env_value = os.environ.get(FOLDERS_ENV, "") if env_value is None else env_value
    candidates: list[tuple[str, str]] = [(folder, "--folder") for folder in folders]
    candidates += [(part, FOLDERS_ENV) for part in env_value.split(os.pathsep) if part.strip()]
    if not any(text.strip() for text, _source in candidates):
        candidates = [(str(start or Path.cwd()), "the working folder")]
    approved: list[Path] = []
    for text, source in candidates:
        text = text.strip().strip('"')
        if not text:
            continue
        if re.match(r"^[A-Za-z]:(?![\\/])", text):
            # "C:" or "C:folder" means the current folder on that drive, which depends on
            # where the process starts; a stray quote after "C:\" also ends up here.
            logger.warning(
                "Ignoring %s %r: name the folder with its full path, such as C:\\Recordings.",
                source,
                text,
            )
            continue
        try:
            folder = _local_path(text).expanduser().resolve(strict=True)
        except OSError:
            logger.warning("Ignoring %s %r: the folder does not exist.", source, text)
            continue
        if not folder.is_dir():
            logger.warning("Ignoring %s %r: not a folder.", source, text)
        elif _too_broad(folder):
            if source != "the working folder":
                logger.warning(
                    "Ignoring %s %r: a drive root or the home folder is never approved "
                    "as a whole; name the folder that holds the recordings.",
                    source,
                    text,
                )
        elif folder not in approved:
            approved.append(folder)
    return approved


# QuickTime and MP4 files start with one of these atoms (ftyp in newer files).
_MP4_ATOMS = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")
# Formats whose files may start with padding or other data before the first frame.
_FRAME_SUFFIXES = (".mp3", ".mpga", ".aac")


def _has_audio_frame(head: bytes) -> bool:
    """Whether an MPEG audio (MP3) or ADTS (AAC) frame sync appears in ``head``."""
    for index in range(len(head) - 1):
        if head[index] == 0xFF and head[index + 1] & 0xE0 == 0xE0:
            return True
    return False


def _looks_like_media(head: bytes, suffix: str = "") -> bool:
    """Whether a file starts like an audio or video container the transcriber reads."""
    if head[4:8] in _MP4_ATOMS:  # MP4, M4A, MOV, M4V
        return True
    if head[:4] in (b"RIFF", b"RF64", b"BW64") and head[8:12] in (b"WAVE", b"AVI "):
        return True
    if head[:4] in (b"OggS", b"fLaC", b"\x1a\x45\xdf\xa3"):  # Ogg/Opus, FLAC, WebM/MKV
        return True
    if head[:3] in (b"ID3", b"FLV") or head[:5] == b"#!AMR":
        return True
    if head[:8] == b"\x30\x26\xb2\x75\x8e\x66\xcf\x11":  # WMA, WMV
        return True
    if head[:4] in (b"\x00\x00\x01\xba", b"\x00\x00\x01\xb3"):  # MPEG program/video stream
        return True
    # An MPEG audio (MP3) or ADTS (AAC) frame: eleven set sync bits, at the start or,
    # for those formats, after leading padding.
    if len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:
        return True
    return suffix in _FRAME_SUFFIXES and _has_audio_frame(head)


def checked_media_file(file_path: str, folders: list[Path]) -> Path:
    """The file to transcribe, once it is a media file inside an approved folder."""
    if not folders:
        raise FileRefusedError(
            "No folder is approved for transcription. Add the folder that holds the "
            "recordings with --folder in the gaik-transcriber server's settings "
            "(setup.bat does this) and restart Claude Desktop."
        )
    try:
        path = _local_path(file_path).expanduser().resolve(strict=True)
    except OSError:
        raise FileRefusedError(f"File not found: {file_path}") from None
    if not any(path.is_relative_to(folder) for folder in folders):
        shown = "; ".join(str(folder) for folder in folders)
        raise FileRefusedError(
            f"{file_path} is outside the folders approved for transcription ({shown}). "
            "Ask the user to move the file there or to approve its folder."
        )
    if not path.is_file():
        raise FileRefusedError(f"{file_path} is not a file.")
    if path.suffix.lower() not in MEDIA_SUFFIXES:
        raise FileRefusedError(
            f"{path.name} is not an audio or video file; the transcriber takes "
            + ", ".join(sorted(MEDIA_SUFFIXES))
            + "."
        )
    with path.open("rb") as handle:
        head = handle.read(4096)
    if not _looks_like_media(head, path.suffix.lower()):
        raise FileRefusedError(f"{path.name} does not contain audio or video.")
    return path


def _hint(exc: Exception) -> str:
    """What to look at for a failed transcription, without the provider's own message."""
    name = type(exc).__name__
    if isinstance(exc, ImportError):
        return "The transcriber is not installed in the server's environment; run setup.bat again."
    if isinstance(exc, FileNotFoundError):
        return "A program it needs was not found; long recordings need FFmpeg on the PATH."
    if any(word in name for word in ("Authentication", "Permission", "Unauthorized")):
        return "The provider refused the key; check the key and, for Azure, the endpoint."
    if any(word in name for word in ("NotFound", "BadRequest")):
        return "The provider refused the request; check the model or deployment name."
    if any(word in name for word in ("RateLimit", "Timeout", "Connection")):
        return "The provider could not be reached or is busy; try again later."
    return "The server's log has the details."


@mcp.tool()
def transcribe_audio(file_path: str, enhanced: bool = False) -> str:
    """
    Transcribe an audio or video file using GAIK Transcriber.

    Only audio and video files inside the folders the user approved for
    transcription are accepted. A refused file returns a message starting with
    "Error:" that says why; tell the user, do not try other paths.

    ==== CRITICAL OUTPUT INSTRUCTIONS ====
    You MUST return the transcription EXACTLY as provided by this tool.

    DO NOT:
    - Add any formatting (headers, bullets, bold, markdown)
    - Restructure or reorganize the text
    - Summarize or paraphrase any part
    - Add section labels or titles
    - Add any commentary before or after
    - Change any words or punctuation

    DO:
    - Output the text exactly as returned
    - Preserve the original flow and structure
    =====================================

    Args:
        file_path: Full Windows path to audio/video file (a /mnt/c/... path is converted)
        enhanced: If True, return enhanced transcript (default: False)

    Returns:
        The exact transcription text - output this verbatim with no changes.
    """
    try:
        path = checked_media_file(file_path, APPROVED)
    except FileRefusedError as refused:
        return f"Error: {refused}"
    try:
        from gaik.software_components.transcriber import Transcriber

        transcriber = Transcriber(api_config=_api_config(), enhanced_transcript=enhanced)
        # The transcriber reports progress with print(); stdout carries the MCP protocol.
        with contextlib.redirect_stdout(sys.stderr):
            result = transcriber.transcribe(file_path=path, custom_context="")
    except Exception as exc:  # noqa: BLE001 - the model gets a short message, the log the rest
        logger.exception("Transcribing %s failed", path.name)
        return f"Error: transcribing {path.name} failed ({type(exc).__name__}). {_hint(exc)}"
    if enhanced and result.enhanced_transcript:
        return result.enhanced_transcript
    return result.raw_transcript


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="GAIK transcriber MCP server")
    parser.add_argument(
        "--folder",
        action="append",
        default=[],
        help="a folder whose audio and video files may be transcribed (repeatable)",
    )
    parser.add_argument(
        "--check-folder",
        metavar="PATH",
        help="print PATH as an approved folder (absolute) and exit; exit 1 if it would be refused",
    )
    args = parser.parse_args(argv)
    if args.check_folder is not None:
        checked = (
            approved_folders([args.check_folder], env_value="") if args.check_folder.strip() else []
        )
        kit = Path(__file__).resolve().parent.parent
        # The folder Claude works in must neither hold this kit nor lie inside it: its
        # tools could then change this server and its virtual environment.
        if not checked or kit.is_relative_to(checked[0]) or checked[0].is_relative_to(kit):
            sys.exit(1)
        print(checked[0])
        sys.exit(0)
    load_settings()
    APPROVED[:] = approved_folders(args.folder)
    if APPROVED:
        logger.info("Transcribing files in: %s", "; ".join(str(f) for f in APPROVED))
    else:
        logger.warning("No folder is approved for transcription; every request is refused.")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
