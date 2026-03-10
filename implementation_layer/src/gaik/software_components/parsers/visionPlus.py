"""VisionPlus parser: Docling structure + vision descriptions, no chunking."""

from __future__ import annotations

import os
import re
from io import BytesIO
from typing import Any

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

from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser


class VisionPlusParser:
    """Parser combining Docling text extraction with vision-based image interpretation.

    Returns markdown and metadata only (no chunking).
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
        vision_prompt: str | None = None,
    ) -> None:
        self.verbose = verbose

        # Defer docling imports to avoid heavy import side-effects at module import time.
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
                "VisionPlusParser requires docling. Install with 'pip install gaik[parser]'"
            ) from exc

        from gaik.software_components.RAG.rag_parser_docling.parser import (
            _build_ocr_options,
            pick_accelerator,
        )

        device = pick_accelerator(verbose=verbose)

        pipeline_kwargs: dict[str, Any] = {
            "do_ocr": enable_ocr,
            "do_table_structure": enable_table_structure,
            "generate_picture_images": True,
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

        self.vision_parser = VisionParser(
            openai_config=vision_config,
            custom_prompt=vision_prompt or self._default_vision_prompt(),
            use_context=False,
            max_tokens=2048,
            temperature=0.0,
        )

    def parse_document(self, file_path: str) -> dict[str, Any]:
        """Parse PDF and return markdown + metadata with image descriptions injected."""
        if self.verbose:
            print(f"Processing PDF with vision enhancement: {file_path}")

        result = self.converter.convert(file_path)
        doc = result.document

        if self.verbose:
            page_count = len(getattr(doc, "pages", [])) or "unknown"
            print(f"Document parsing complete. Pages: {page_count}")

        images_with_positions = self._collect_images(doc)
        if self.verbose:
            print(f"Found {len(images_with_positions)} images to analyze")

        image_descriptions, descriptions_by_page = self._describe_images(images_with_positions)

        markdown_text = doc.export_to_markdown(image_mode="embedded")
        markdown_text = self._replace_images_with_descriptions(markdown_text, image_descriptions)

        source_file = os.path.basename(file_path)
        metadata = {
            "source": file_path,
            "source_file": source_file,
            "page_count": len(getattr(doc, "pages", [])) if hasattr(doc, "pages") else None,
            "image_count": len(images_with_positions),
            "pages_with_images": sorted(descriptions_by_page.keys()),
            "parsing_method": "visionPlus",
            "format_used": "markdown",
        }

        return {
            "source_file": source_file,
            "parsed_markdown": markdown_text,
            "metadata": metadata,
        }

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

    @staticmethod
    def _replace_images_with_descriptions(markdown_text: str, descriptions: dict[int, str]) -> str:
        pattern = r"!\[.*?\]\(data:image\/png;base64,[A-Za-z0-9+/=\n]+\)"
        counter = [0]

        def replacement(_match):
            idx = counter[0]
            counter[0] += 1
            if idx in descriptions:
                desc = descriptions[idx]
                return f"\n\n**[IMAGE DESCRIPTION]**\n{desc}\n\n"
            return "\n\n[Image: No description available]\n\n"

        return re.sub(pattern, replacement, markdown_text)

    @staticmethod
    def _default_vision_prompt() -> str:
        return (
            "Analyze this image from a document and provide a concise interpretation.\n\n"
            "**If this is a CHART, GRAPH, or DATA VISUALIZATION:**\n"
            "1. State the title and subtitle if visible\n"
            "2. Provide a concise interpretation with key insights.\n\n"
            "**If this is a DIAGRAM or INFOGRAPHIC:**\n"
            "1. Provide a concise interpretation with key insights.\n\n"
            "**If this is a PHOTOGRAPH or ILLUSTRATION:**\n"
            "1. Briefly mention what is shown\n\n"
            "**Format your response as:**\n"
            "[Type]: [Title/Description]\n"
            "- Key insight 1\n"
            "- Key insight 2 (optional)\n"
        )


def parse_document_with_vision_plus(
    file_path: str, *, vision_config: OpenAIConfig | dict
) -> dict[str, Any]:
    """Convenience wrapper for VisionPlusParser."""
    parser = VisionPlusParser(vision_config=vision_config)
    return parser.parse_document(file_path)
