"""Docling-based parser utilities for RAG workflows."""

from __future__ import annotations

import os
import re
from collections import OrderedDict
from typing import TYPE_CHECKING

# Patch transformers export for AutoProcessor before docling imports.
try:
    import transformers as _tf

    if not hasattr(_tf, "AutoProcessor"):
        from transformers.models.auto.processing_auto import AutoProcessor as _AutoProcessor

        _tf.AutoProcessor = _AutoProcessor
        if hasattr(_tf, "__all__") and isinstance(_tf.__all__, list):
            if "AutoProcessor" not in _tf.__all__:
                _tf.__all__.append("AutoProcessor")
except Exception:
    pass

try:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        EasyOcrOptions,
        PdfPipelineOptions,
        RapidOcrOptions,
        TableStructureOptions,
        TesseractCliOcrOptions,
        TesseractOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
except ImportError as exc:
    raise ImportError(
        "rag_parser_docling requires the 'docling' package. "
        "Install extras with 'pip install gaik[rag-parser-docling]'"
    ) from exc

if TYPE_CHECKING:
    from langchain_core.documents import Document

try:
    import torch  # type: ignore

    _HAS_TORCH = True
except Exception:
    _HAS_TORCH = False

# Optional summaries import (kept from existing behavior).
try:
    from src.summaries_images import summaries

    summaries = OrderedDict(summaries)
except Exception:
    summaries = OrderedDict()


def _torch_status() -> dict:
    """Return a dict with Torch/CUDA status."""
    info = {
        "torch_import_ok": False,
        "torch_version": None,
        "cuda_available": False,
        "cuda_device_count": 0,
        "cuda_device_name": None,
    }

    if not _HAS_TORCH:
        return info

    try:
        info["torch_import_ok"] = True
        info["torch_version"] = getattr(torch, "__version__", None)
        if torch.cuda.is_available():
            info["cuda_available"] = True
            info["cuda_device_count"] = torch.cuda.device_count()
            try:
                idx = torch.cuda.current_device()
            except Exception:
                idx = 0
            try:
                info["cuda_device_name"] = torch.cuda.get_device_name(idx)
            except Exception:
                info["cuda_device_name"] = None
    except Exception:
        pass

    return info


def pick_accelerator(verbose: bool = True) -> AcceleratorDevice:
    """
    Select the best available accelerator:
      - CUDA if a CUDA-enabled PyTorch build is present and available
      - CPU otherwise
    """
    status = _torch_status()

    if verbose:
        if status["torch_import_ok"]:
            print(
                f"[Torch] version: {status['torch_version']}, "
                f"cuda available: {status['cuda_available']}"
            )
        else:
            print("[Torch] not installed or failed to import")

    if status["cuda_available"]:
        if verbose:
            name = status["cuda_device_name"] or "Unknown NVIDIA GPU"
            print(f"Using CUDA device: {name} (devices: {status['cuda_device_count']})")
        return AcceleratorDevice.CUDA

    if verbose:
        print("CUDA not available. Using CPU.")
    return AcceleratorDevice.CPU


class DoclingRagParser:
    """Docling-based parser for RAG pipelines."""

    def __init__(
        self,
        *,
        enable_ocr: bool = True,
        ocr_engine: str = "tesseract_cli",
        enable_table_structure: bool = True,
        enable_formula_enrichment: bool = True,
        num_threads: int = 4,
        verbose: bool = True,
    ) -> None:
        self.summaries = summaries.copy()

        device = pick_accelerator(verbose=verbose)

        pipeline_kwargs = {
            "do_ocr": enable_ocr,
            "do_table_structure": enable_table_structure,
            "generate_picture_images": False,
            "generate_page_images": False,
            "do_formula_enrichment": enable_formula_enrichment,
            "table_structure_options": TableStructureOptions(
                kind="docling_tableformer",
                do_cell_matching=True,
            )
            if enable_table_structure
            else None,
            "accelerator_options": AcceleratorOptions(
                num_threads=num_threads,
                device=device,
            ),
        }
        if enable_ocr:
            pipeline_kwargs["ocr_options"] = _build_ocr_options(ocr_engine)

        self.pipeline_options = PdfPipelineOptions(**pipeline_kwargs)

        self.format_options = {
            InputFormat.PDF: PdfFormatOption(pipeline_options=self.pipeline_options)
        }
        self.converter = DocumentConverter(format_options=self.format_options)
        self.supported_extensions = [".pdf"]

    def replace_base64_images(self, md_text: str, summary_dict: OrderedDict) -> str:
        pattern = r"!\[.*?\]\(data:image\/png;base64,[A-Za-z0-9+/=\n]+\)"

        def replacement(_match):
            if summary_dict:
                _, value = summary_dict.popitem(last=False)
                return f"\n\n{value}\n\n"
            return "\n\n[Image removed - no summary available]\n\n"

        return re.sub(pattern, replacement, md_text)

    def convert_pdf_to_markdown(self, pdf_path: str, output_path: str | None = None) -> str:
        if output_path is None:
            pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
            output_path = os.path.join(os.path.dirname(pdf_path), f"{pdf_name}.md")

        result = self.converter.convert(pdf_path)
        markdown_text = result.document.export_to_markdown(image_mode="embedded")
        markdown_text = self.replace_base64_images(markdown_text, self.summaries.copy())

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        return markdown_text

    def convert_pdf_to_chunks_with_metadata(
        self, pdf_path: str
    ) -> list[Document]:
        """
        Convert PDF to chunks with metadata including document name and page numbers.
        Returns a list of LangChain Document objects with metadata.

        Note: This method uses Docling's HierarchicalChunker, which chunks by document
        structure (headings, sections, paragraphs) rather than by fixed size. Chunk
        boundaries are determined by the document's semantic structure.
        """
        print(f"Processing document with metadata extraction: {pdf_path}")
        print("Parsing document(s)...")
        result = self.converter.convert(pdf_path)
        doc = result.document
        print(f"Document parsing complete. Pages: {len(getattr(doc, 'pages', [])) or 'unknown'}")

        try:
            from docling.chunking import HierarchicalChunker
        except ImportError as exc:
            raise ImportError(
                "Docling chunking is required for this method. "
                "Install extras with 'pip install docling-core[chunking]'"
            ) from exc

        try:
            from langchain_core.documents import Document
        except ImportError as exc:
            raise ImportError(
                "rag_parser_docling requires 'langchain-core' for chunk output. "
                "Install extras with 'pip install gaik[rag-parser-docling]'"
            ) from exc

        # HierarchicalChunker chunks by document structure (headings, sections)
        # rather than by fixed size. Chunk boundaries follow semantic structure.
        chunker = HierarchicalChunker()
        document_name = os.path.splitext(os.path.basename(pdf_path))[0]
        langchain_docs: list[Document] = []
        chunk_id = 0

        for chunk in chunker.chunk(doc):
            try:
                chunk_text = chunk.text
                chunk_dict = chunk.model_dump()

                filename = document_name
                if "meta" in chunk_dict and "origin" in chunk_dict["meta"]:
                    origin_filename = chunk_dict["meta"]["origin"].get("filename")
                    if origin_filename:
                        filename = os.path.splitext(os.path.basename(origin_filename))[0]

                page_num = None
                if (
                    "meta" in chunk_dict
                    and "doc_items" in chunk_dict["meta"]
                    and chunk_dict["meta"]["doc_items"]
                    and "prov" in chunk_dict["meta"]["doc_items"][0]
                    and chunk_dict["meta"]["doc_items"][0]["prov"]
                ):
                    page_num = chunk_dict["meta"]["doc_items"][0]["prov"][0].get("page_no")

                heading = None
                if (
                    "meta" in chunk_dict
                    and "headings" in chunk_dict["meta"]
                    and chunk_dict["meta"]["headings"]
                ):
                    heading = chunk_dict["meta"]["headings"][0]

                metadata = {
                    "source": pdf_path,
                    "document_name": filename,
                    "page_number": page_num if page_num is not None else "Unknown",
                    "heading": heading,
                    "chunk_id": chunk_id,
                }

                langchain_docs.append(Document(page_content=chunk_text, metadata=metadata))
                chunk_id += 1

                if chunk_id <= 3:
                    print(
                        f"Chunk {chunk_id}: document='{filename}', "
                        f"page={page_num}, heading='{heading}'"
                    )

            except Exception as exc:
                print(f"Error processing chunk {chunk_id}: {exc}")
                fallback_meta = {
                    "source": pdf_path,
                    "document_name": document_name,
                    "page_number": "Unknown",
                    "heading": None,
                    "chunk_id": chunk_id,
                }
                langchain_docs.append(
                    Document(page_content=getattr(chunk, "text", ""), metadata=fallback_meta)
                )
                chunk_id += 1

        print(f"Created {len(langchain_docs)} chunks with metadata from {document_name}")
        return langchain_docs


def parse_pdf_to_markdown(pdf_path: str, output_path: str | None = None) -> str:
    """Convenience wrapper for DoclingRagParser.convert_pdf_to_markdown."""
    parser = DoclingRagParser()
    return parser.convert_pdf_to_markdown(pdf_path, output_path=output_path)


def parse_pdf_to_chunks_with_metadata(pdf_path: str) -> list[Document]:
    """
    Convenience wrapper for DoclingRagParser.convert_pdf_to_chunks_with_metadata.

    Chunks documents by structure (headings, sections) using HierarchicalChunker.
    """
    parser = DoclingRagParser()
    return parser.convert_pdf_to_chunks_with_metadata(pdf_path)


def _build_ocr_options(ocr_engine: str):
    engine = (ocr_engine or "").lower()
    if engine == "tesseract":
        return TesseractOcrOptions()
    if engine == "tesseract_cli":
        return TesseractCliOcrOptions()
    if engine == "easyocr":
        return EasyOcrOptions()
    if engine == "rapidocr":
        return RapidOcrOptions()
    raise ValueError(
        "Unsupported OCR engine. Use 'tesseract_cli', 'tesseract', 'easyocr', or 'rapidocr'."
    )
