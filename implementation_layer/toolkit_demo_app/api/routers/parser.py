"""Parser router - Document parsing endpoints"""

import os
import tempfile
from pathlib import Path
from typing import Literal

try:
    from utils import get_api_config, validate_file_size, validate_vision_page_limit
except ImportError:
    from api.utils import (
        get_api_config,
        validate_file_size,
        validate_vision_page_limit,
    )
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

try:
    from utils.model_settings import provider_error_detail
except ImportError:
    from api.utils.model_settings import provider_error_detail

try:
    from utils.config import get_model_options
    from utils.model_settings import get_request_api_config
except ImportError:
    from api.utils.config import get_model_options
    from api.utils.model_settings import get_request_api_config

router = APIRouter()


@router.post("")
async def parse_document(
    file: UploadFile = File(...),
    parser_type: Literal[
        "auto", "pymupdf", "docx", "vision", "vision_plus", "docling_api", "multimodal"
    ] = Form("docling_api"),
):
    """
    Parse a document (PDF, DOCX, or image) and extract text content.

    - **file**: The document or image file to parse
    - **parser_type**: Parser to use (auto, pymupdf, docx, vision, vision_plus,
      docling_api, multimodal)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    supported_docs = [".pdf", ".docx"]
    supported_images = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"]

    if suffix not in supported_docs + supported_images:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type: {suffix}. "
                f"Supported: {', '.join(supported_docs + supported_images)}"
            ),
        )

    # Validate file size and save temporarily
    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Auto-detect parser type
        if parser_type == "auto":
            if suffix == ".docx":
                parser_type = "docx"
            elif suffix in supported_images:
                parser_type = "vision"
            else:
                parser_type = "pymupdf"

        validate_vision_page_limit(tmp_path, suffix, parser_type)

        if parser_type == "docx":
            from gaik.software_components.parsers import DocxParser

            parser = DocxParser()
            result = parser.parse_document(tmp_path)
        elif parser_type == "pymupdf":
            from gaik.software_components.parsers import PyMuPDFParser

            parser = PyMuPDFParser()
            result = parser.parse_document(tmp_path)
        elif parser_type == "vision":
            from gaik.software_components.parsers import VisionParser

            vision_config = get_api_config()
            parser = VisionParser(openai_config=vision_config, **get_model_options(vision_config))
            # VisionParser uses convert_pdf() which returns list of markdown pages
            markdown_pages = (
                parser.convert_pdf(tmp_path)
                if suffix == ".pdf"
                else [parser.convert_image(tmp_path)]
            )
            result = {"text_content": "\n\n".join(markdown_pages), "metadata": {}}
        elif parser_type == "vision_plus":
            from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

            vision_config = get_api_config()
            parser = VisionRagParser(
                vision_config=vision_config,
                verbose=False,
                save_markdown=False,
                enable_ocr=False,
                enable_table_structure=True,
                enable_formula_enrichment=False,
            )
            # Convert to markdown (we don't need the chunks)
            markdown, _chunks = parser.convert_doc_to_chunks_with_vision(
                tmp_path, return_markdown=True
            )
            result = {"text_content": markdown, "metadata": {"parser": "vision_plus"}}
        elif parser_type == "multimodal":
            if suffix != ".pdf":
                raise HTTPException(
                    status_code=400,
                    detail="Multimodal parser currently supports PDF files only",
                )

            from gaik.software_components.parsers import MultimodalParser

            # Use the shared deployment model unless a parser-specific model is configured.
            # Override with AZURE_MULTIMODAL_DEPLOYMENT without redeploy.
            request_config = get_request_api_config()
            config = request_config or get_api_config()
            if request_config is None and os.getenv("AZURE_MULTIMODAL_DEPLOYMENT"):
                config = {**config, "model": os.environ["AZURE_MULTIMODAL_DEPLOYMENT"]}
            parser = MultimodalParser(
                api_config=config,
                model=config["model"],
                reasoning_effort=get_model_options(config)["reasoning_effort"],
                merge_table=True,
                create_html=False,
            )
            parse_result = parser.parse(tmp_path)
            usage = parse_result.usage
            metadata: dict = {"parser": "multimodal"}
            if usage is not None:
                metadata.update(
                    {
                        "provider": usage.provider,
                        "model": usage.model,
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "thinking_tokens": usage.thinking_tokens,
                        "total_tokens": usage.total_tokens,
                        "duration_s": usage.duration_s,
                        "cost_usd": usage.cost_usd,
                    }
                )
            result = {
                "text_content": parse_result.clean_markdown,
                "metadata": metadata,
            }
        elif parser_type == "docling_api":
            from gaik.software_components.parsers import PyMuPDFParser
            from gaik.software_components.parsers.docling_api_client import DoclingApiClientParser

            api_base = os.getenv("DOCLING_API_BASE")
            password = os.getenv("DOCLING_API_PASSWORD")
            if api_base and password:
                try:
                    parser = DoclingApiClientParser(api_base=api_base, password=password)
                    result_raw = parser.parse_document(tmp_path)
                    parsed_markdown = result_raw.get("parsed_markdown", "")
                    if parsed_markdown:
                        result = {
                            "text_content": parsed_markdown,
                            "metadata": {
                                **result_raw.get("metadata", {}),
                                "source_file": result_raw.get("source_file", ""),
                                "elapsed_seconds": result_raw.get("elapsed_seconds"),
                                "parser": "docling_api",
                            },
                        }
                    else:
                        raise ValueError("HH Parser returned empty markdown")
                except Exception as exc:
                    # PyMuPDF reads PDFs only. Falling back for a DOCX replaced
                    # the service's error with a misleading "PDF only" 500.
                    if suffix != ".pdf":
                        raise HTTPException(
                            status_code=502,
                            detail=f"HH Parser could not parse this {suffix} file: {exc}",
                        ) from exc
                    parser = PyMuPDFParser()
                    result = parser.parse_document(tmp_path)
                    result.setdefault("metadata", {})["parser"] = "pymupdf"
            else:
                if suffix != ".pdf":
                    raise HTTPException(
                        status_code=503,
                        detail="HH Parser is not configured; only PDF files can be parsed.",
                    )
                parser = PyMuPDFParser()
                result = parser.parse_document(tmp_path)
                result.setdefault("metadata", {})["parser"] = "pymupdf"
        else:
            raise HTTPException(status_code=400, detail=f"Unknown parser: {parser_type}")

        return {
            "filename": file.filename,
            "parser": parser_type,
            "text_content": result.get("text_content", ""),
            "metadata": result.get("metadata", {}),
        }

    except HTTPException:
        # Keep the status this router chose; the catch-all below would turn a
        # 400 (wrong file type, too many pages) into a 500.
        raise
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Parser not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=provider_error_detail(e)) from e
    finally:
        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)
