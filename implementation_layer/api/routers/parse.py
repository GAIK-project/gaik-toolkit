"""Parse endpoint for document processing."""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from gaik.software_components.parsers import DocxParser, PyMuPDFParser, VisionParser

from implementation_layer.api.config import get_openai_config, settings
from implementation_layer.api.dependencies import verify_api_key
from implementation_layer.api.schemas.parse import ParseResponse
from implementation_layer.api.utils import temp_file, validate_file_size, validate_upload

router = APIRouter()

ParserType = Literal["auto", "pymupdf", "docx", "vision", "multimodal"]


def select_parser(parser_type: str, suffix: str) -> str:
    """Select the actual parser based on type and file extension."""
    if parser_type == "auto":
        return "docx" if suffix == ".docx" else "pymupdf"
    return parser_type


def parse_with_docx(file_path: str) -> tuple[str, dict]:
    """Parse document using DocxParser."""
    parser = DocxParser()
    result = parser.parse_document(file_path)
    return result.get("text_content", ""), result.get("metadata", {})


def parse_with_pymupdf(file_path: str) -> tuple[str, dict]:
    """Parse document using PyMuPDFParser."""
    parser = PyMuPDFParser()
    result = parser.parse_document(file_path)
    return result.get("text_content", ""), result.get("metadata", {})


def parse_with_vision(file_path: str) -> tuple[str, dict]:
    """Parse document using VisionParser with LLM."""
    config = get_openai_config()
    openai_config = {
        "api_key": config["api_key"],
        "model": config["model"],
        "use_azure": config["use_azure"],
    }
    if config["use_azure"]:
        openai_config["azure_endpoint"] = config["azure_endpoint"]
        openai_config["api_version"] = config["api_version"]

    parser = VisionParser(openai_config=openai_config)
    pages = parser.convert_pdf(file_path, clean_output=True)
    return "\n\n".join(pages), {"pages": len(pages), "parser": "vision"}


def parse_with_multimodal(file_path: str) -> tuple[str, dict]:
    """Parse PDF using MultimodalParser (layout-aware OpenAI/Azure markdown)."""
    from gaik.software_components.parsers import MultimodalParser

    parser = MultimodalParser(
        model_provider="openai",
        use_azure=settings.USE_AZURE,
        reasoning_effort="low",
        create_html=False,
    )
    result = parser.parse(file_path)
    metadata: dict = {"parser": "multimodal", "model_provider": "openai"}
    if result.usage:
        metadata["model"] = result.usage.model
        metadata["duration_seconds"] = result.usage.duration_s
        metadata["tokens"] = {
            "input": result.usage.input_tokens,
            "output": result.usage.output_tokens,
            "total": result.usage.total_tokens,
        }
        metadata["cost_usd"] = result.usage.cost_usd
    return result.clean_markdown, metadata


PARSERS = {
    "docx": parse_with_docx,
    "pymupdf": parse_with_pymupdf,
    "vision": parse_with_vision,
    "multimodal": parse_with_multimodal,
}


@router.post(
    "/",
    response_model=ParseResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Parse document",
    description="Parse a PDF or DOCX document and extract text content.",
)
async def parse_document(
    file: UploadFile = File(..., description="Document file (PDF or DOCX)"),
    parser_type: ParserType = Form(
        default="auto",
        description="Parser type: auto | pymupdf | docx | vision | multimodal",
    ),
):
    """
    Parse a document (PDF or DOCX) and extract text content.

    - **file**: PDF or DOCX file
    - **parser_type**:
        - auto: Automatically select based on file type (pymupdf for PDF, docx for DOCX)
        - pymupdf: Fast local PDF parsing (text only)
        - docx: Word document parsing
        - vision: LLM-based PDF to Markdown page by page (requires OpenAI)
        - multimodal: Layout-aware LLM parsing with clean Markdown output (requires OpenAI)

    Returns extracted text content and metadata.
    """
    suffix = validate_upload(file, settings.ALLOWED_DOC_EXTENSIONS)

    content = await file.read()
    validate_file_size(content)

    with temp_file(content, suffix) as tmp_path:
        try:
            actual_parser = select_parser(parser_type, suffix)

            parse_func = PARSERS.get(actual_parser)
            if not parse_func:
                raise HTTPException(status_code=400, detail=f"Unknown parser type: {parser_type}")

            if actual_parser in {"vision", "multimodal"} and suffix != ".pdf":
                raise HTTPException(
                    status_code=400,
                    detail=f"Parser '{actual_parser}' supports PDF only.",
                )

            text_content, metadata = parse_func(tmp_path)
            metadata["word_count"] = len(text_content.split())

            return ParseResponse(
                filename=file.filename,
                parser=actual_parser,
                text_content=text_content,
                metadata=metadata,
            )

        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="Parser not available. Required dependencies missing.",
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="Parsing failed")
