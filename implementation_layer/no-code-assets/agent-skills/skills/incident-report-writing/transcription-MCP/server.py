"""MCP Server for GAIK Transcriber"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from gaik.software_components.transcriber import Transcriber, get_openai_config
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).with_name(".env"))

# Initialize MCP server
mcp = FastMCP("gaik-transcriber")


def _api_config() -> dict:
    """OpenAI or Azure OpenAI settings, as setup.bat wrote them to .env."""
    use_azure = os.getenv("OPENAI_API_TYPE", "").strip().lower() == "azure" or (
        not os.getenv("OPENAI_API_KEY") and bool(os.getenv("AZURE_API_KEY"))
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


@mcp.tool()
def transcribe_audio(file_path: str, enhanced: bool = False) -> str:
    """
    Transcribe audio/video file using GAIK Transcriber.

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
        config = _api_config()

        transcriber = Transcriber(
            api_config=config,
            enhanced_transcript=enhanced,
        )

        result = transcriber.transcribe(
            file_path=_local_path(file_path),
            custom_context="",
        )

        if enhanced and result.enhanced_transcript:
            return result.enhanced_transcript

        return result.raw_transcript

    except Exception as e:
        import traceback

        error_msg = f"Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        return error_msg


if __name__ == "__main__":
    mcp.run(transport="stdio")
