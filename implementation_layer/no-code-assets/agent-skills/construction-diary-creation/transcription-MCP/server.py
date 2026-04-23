"""MCP Server for GAIK Transcriber"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from gaik.software_components.transcriber import Transcriber, get_openai_config
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).with_name(".env"))

# Initialize MCP server
mcp = FastMCP("gaik-transcriber")

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
        file_path: Full Windows path to audio/video file
        enhanced: If True, return enhanced transcript (default: False)

    Returns:
        The exact transcription text - output this verbatim with no changes.
    """
    try:
        config = get_openai_config(use_azure=False)

        transcriber = Transcriber(
            api_config=config,
            enhanced_transcript=enhanced,
        )

        result = transcriber.transcribe(
            file_path=Path(file_path),
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

