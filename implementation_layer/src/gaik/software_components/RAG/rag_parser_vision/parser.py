"""Vision-enhanced RAG parser utilities.

Combines Docling's structure analysis with vision models for image interpretation.
"""

from __future__ import annotations

import os
from io import BytesIO
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from langchain_core.documents import Document

# Note: All docling imports are deferred to __init__ to avoid
# torch DLL loading issues on Windows at module import time

try:
    from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser
except ImportError as exc:
    raise ImportError(
        "rag_parser_vision requires the 'vision' parser. "
        "Install extras with 'pip install gaik[rag-parser-vision]'"
    ) from exc


class VisionRagParser:
    """RAG parser combining Docling structure analysis with vision model interpretations.

    This parser uses:
    - Docling: Fast, accurate text extraction and document structure analysis
    - Vision Model: AI-powered interpretation of images, charts, and diagrams

    The combination provides the best of both worlds:
    - Accurate text extraction without hallucination
    - Detailed descriptions of visual content
    - Proper positioning of image descriptions in document structure
    """

    def __init__(
        self,
        *,
        vision_config: OpenAIConfig | dict,
        enable_ocr: bool = True,
        ocr_engine: str = "tesseract_cli",
        enable_table_structure: bool = True,
        enable_formula_enrichment: bool = True,
        num_threads: int = 4,
        verbose: bool = True,
        save_markdown: bool = False,
        vision_prompt: str | None = None,
    ) -> None:
        """
        Initialize the VisionRagParser.

        Args:
            vision_config: OpenAI/Azure OpenAI configuration for vision model
            enable_ocr: Enable OCR for scanned documents (Docling)
            ocr_engine: OCR engine to use ('tesseract_cli', 'tesseract', 'easyocr', 'rapidocr')
            enable_table_structure: Enable table structure extraction (Docling)
            enable_formula_enrichment: Enable formula/equation enrichment (Docling)
            num_threads: Number of threads for processing (Docling)
            verbose: Print verbose output
            save_markdown: Persist markdown output when output_path is provided
            vision_prompt: Custom prompt for vision model (defaults to chart/diagram analysis)
        """
        self.verbose = verbose
        self.save_markdown = save_markdown

        # Import docling modules here to avoid torch DLL issues on Windows
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                AcceleratorOptions,
                PdfPipelineOptions,
                TableStructureOptions,
            )
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise ImportError(
                "rag_parser_vision requires the 'docling' package. "
                "Install extras with 'pip install gaik[rag-parser-vision]'"
            ) from exc

        # Initialize Docling with image extraction enabled
        from gaik.software_components.RAG.rag_parser_docling.parser import (
            _build_ocr_options,
            pick_accelerator,
        )

        device = pick_accelerator(verbose=verbose)

        pipeline_kwargs = {
            "do_ocr": enable_ocr,
            "do_table_structure": enable_table_structure,
            "generate_picture_images": True,  # Must be True to extract images
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

        # Initialize Vision Parser
        self.vision_parser = VisionParser(
            openai_config=vision_config,
            custom_prompt=vision_prompt or self._default_vision_prompt(),
            use_context=False,  # We handle context via Docling structure
            max_tokens=2048,
            temperature=0.0,
        )

    def convert_doc_to_chunks_with_vision(
        self,
        pdf_path: str,
        *,
        document_name: str | None = None,
        output_path: str | None = None,
        return_markdown: bool = False,
    ) -> list[Document] | tuple[str, list[Document]]:
        """
        Convert PDF to RAG chunks with AI-generated image descriptions.

        This method:
        1. Uses Docling to extract document structure and images
        2. Sends images to vision model for detailed descriptions
        3. Appends descriptions to chunk text by page
        4. Chunks by document structure using HierarchicalChunker

        Args:
            pdf_path: Path to PDF file
            document_name: Optional document name override (uses filename from path if not provided)

        Returns:
            List of LangChain Document objects with metadata, or (markdown, chunks)
        """
        result, markdown_text, descriptions_by_page = self._convert_with_vision(pdf_path)
        self._maybe_save_markdown(markdown_text, output_path)
        doc = result.document

        try:
            from langchain_core.documents import Document
        except ImportError as exc:
            raise ImportError(
                "rag_parser_vision requires 'langchain-core' for chunk output. "
                "Install extras with 'pip install gaik[rag-parser-vision]'"
            ) from exc

        try:
            from docling.chunking import HierarchicalChunker
        except ImportError as exc:
            raise ImportError(
                "Docling chunking is required for this method. "
                "Install extras with 'pip install docling-core[chunking]'"
            ) from exc

        chunker = HierarchicalChunker()
        # Use provided document_name or extract from path
        doc_name = document_name or os.path.splitext(os.path.basename(pdf_path))[0]
        langchain_docs: list[Document] = []
        chunk_id = 0

        for chunk in chunker.chunk(doc):
            try:
                chunk_text = chunk.text or ""
                chunk_dict = chunk.model_dump()

                filename = doc_name
                # Only use origin filename if document_name wasn't explicitly provided
                if not document_name and "meta" in chunk_dict and "origin" in chunk_dict["meta"]:
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

                if page_num is not None and page_num in descriptions_by_page:
                    desc_block = "\n\n[IMAGE DESCRIPTIONS]\n" + "\n\n".join(
                        descriptions_by_page[page_num]
                    )
                    chunk_text = f"{chunk_text}{desc_block}"

                metadata = {
                    "source": pdf_path,
                    "document_name": filename,
                    "page_number": page_num if page_num is not None else "Unknown",
                    "heading": heading,
                    "chunk_id": chunk_id,
                }

                langchain_docs.append(Document(page_content=chunk_text, metadata=metadata))
                chunk_id += 1

                if self.verbose and chunk_id <= 3:
                    print(
                        f"Chunk {chunk_id}: document='{filename}', "
                        f"page={page_num}, heading='{heading}'"
                    )

            except Exception as exc:
                if self.verbose:
                    print(f"Error processing chunk {chunk_id}: {exc}")
                fallback_meta = {
                    "source": pdf_path,
                    "document_name": doc_name,
                    "page_number": "Unknown",
                    "heading": None,
                    "chunk_id": chunk_id,
                }
                langchain_docs.append(
                    Document(page_content=getattr(chunk, "text", ""), metadata=fallback_meta)
                )
                chunk_id += 1

        if self.verbose:
            print(
                f"Created {len(langchain_docs)} chunks with vision-enhanced content from {doc_name}"
            )

        if return_markdown:
            return markdown_text, langchain_docs
        return langchain_docs

    def _convert_with_vision(
        self, pdf_path: str
    ) -> tuple[Any, str, dict[int, list[str]]]:
        if self.verbose:
            print(f"Processing PDF with vision enhancement: {pdf_path}")

        result = self.converter.convert(pdf_path)
        doc = result.document

        if self.verbose:
            print(
                f"Document parsing complete. Pages: "
                f"{len(getattr(doc, 'pages', [])) or 'unknown'}"
            )

        images_with_positions = self._collect_images(doc)
        if self.verbose:
            print(f"Found {len(images_with_positions)} images to analyze")

        image_descriptions, descriptions_by_page = self._describe_images(images_with_positions)

        markdown_text = result.document.export_to_markdown(image_mode="embedded")
        markdown_text = self._replace_images_with_descriptions(
            markdown_text, image_descriptions
        )

        return result, markdown_text, descriptions_by_page

    def _maybe_save_markdown(self, markdown_text: str, output_path: str | None) -> None:
        if not self.save_markdown:
            return
        if not output_path:
            return
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        if self.verbose:
            print(f"Markdown saved to: {output_path}")

    def _collect_images(self, doc) -> list[dict[str, Any]]:
        images_with_positions: list[dict[str, Any]] = []
        for entry in doc.iterate_items():
            item = entry[0] if isinstance(entry, tuple) else entry
            if item.label == "picture" and hasattr(item, "image") and item.image:
                page_num = None
                if item.prov and len(item.prov) > 0:
                    page_num = item.prov[0].page_no

                images_with_positions.append(
                    {
                        "image": item.image,
                        "page": page_num,
                        "item_ref": id(item),
                    }
                )
        return images_with_positions

    def _describe_images(
        self, images_with_positions: list[dict[str, Any]]
    ) -> tuple[dict[int, str], dict[int, list[str]]]:
        image_descriptions: dict[int, str] = {}
        descriptions_by_page: dict[int, list[str]] = {}

        for idx, img_data in enumerate(images_with_positions, start=1):
            if self.verbose:
                print(
                    f"Analyzing image {idx}/{len(images_with_positions)} (page {img_data['page']})"
                )

            img_bytes = self._pil_to_bytes(img_data["image"])
            if not img_bytes:
                if self.verbose:
                    print("  X Failed to convert image to bytes")
                image_descriptions[idx - 1] = "[Image: Description unavailable]"
                continue

            try:
                description = self.vision_parser._parse_image(
                    img_bytes, page=img_data["page"] or 0, previous_context=None
                )
                image_descriptions[idx - 1] = description
                if img_data["page"] is not None:
                    descriptions_by_page.setdefault(img_data["page"], []).append(description)
                if self.verbose:
                    print("  OK Generated description")
            except Exception as exc:
                if self.verbose:
                    print(f"  X Failed to analyze image: {exc}")
                image_descriptions[idx - 1] = "[Image: Description unavailable]"

        return image_descriptions, descriptions_by_page

    def _pil_to_bytes(self, image_obj) -> bytes:
        """Convert image-like objects to PNG bytes."""
        pil_image = self._as_pil_image(image_obj)
        if pil_image is None:
            return b""
        buffered = BytesIO()
        pil_image.save(buffered, format="PNG")
        return buffered.getvalue()

    @staticmethod
    def _as_pil_image(image_obj):
        if image_obj is None:
            return None
        if hasattr(image_obj, "save"):
            return image_obj
        if hasattr(image_obj, "pil_image"):
            pil = getattr(image_obj, "pil_image")
            if hasattr(pil, "save"):
                return pil
        if hasattr(image_obj, "image"):
            pil = getattr(image_obj, "image")
            if hasattr(pil, "save"):
                return pil
        if hasattr(image_obj, "to_pil"):
            try:
                pil = image_obj.to_pil()
                if hasattr(pil, "save"):
                    return pil
            except Exception:
                return None
        return None

    def _replace_images_with_descriptions(
        self, markdown_text: str, descriptions: dict[int, str]
    ) -> str:
        """Replace base64 images in markdown with text descriptions."""
        import re

        pattern = r"!\[.*?\]\(data:image\/png;base64,[A-Za-z0-9+/=\n]+\)"
        counter = [0]  # Mutable container for closure

        def replacement(match):  # noqa: ARG001
            idx = counter[0]
            counter[0] += 1
            if idx in descriptions:
                desc = descriptions[idx]
                return f"\n\n**[IMAGE DESCRIPTION]**\n{desc}\n\n"
            return "\n\n[Image: No description available]\n\n"

        return re.sub(pattern, replacement, markdown_text)

    @staticmethod
    def _default_vision_prompt() -> str:
        """Default prompt optimized for charts, diagrams, and infographics."""
        return (
            "Analyze this image from a document and provide a concise interpretation.\n\n"
            "**If this is a CHART, GRAPH, or DATA VISUALIZATION:**\n"
            "1. State the title and subtitle if visible\n"
            "2. Provide a concise interpretation with key insights."
            "The key insights should be sufficient to answer any question.\n\n"
            "**If this is a DIAGRAM or INFOGRAPHIC:**\n"
            "1. Provide a concise interpretation with key insights. "
            "The key insights should be sufficient to answer any question.\n\n"
            "**If this is a PHOTOGRAPH or ILLUSTRATION:**\n"
            "1. Briefly mention what is shown\n\n"
            "**Format your response as:**\n"
            "[Type]: [Title/Description]\n"
            "- Key insight 1\n"
            "- Key insight 2 (optional)\n\n"
            "Keep the response short and focused."
        )


def parse_doc_to_chunks_with_vision(
    pdf_path: str, vision_config: OpenAIConfig | dict
) -> list[Document]:
    """
    Convenience function to convert PDF to RAG chunks with vision descriptions.

    Args:
        pdf_path: Path to PDF file
        vision_config: OpenAI/Azure OpenAI configuration

    Returns:
        List of LangChain Document objects with metadata
    """
    parser = VisionRagParser(vision_config=vision_config)
    return parser.convert_doc_to_chunks_with_vision(pdf_path)
