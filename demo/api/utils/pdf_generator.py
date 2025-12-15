"""
Generate PDF documents from structured data.
Copied from gaik.software_components.structured_data_to_pdf for demo use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None  # type: ignore


@dataclass
class PDFResult:
    """Result from PDF generation."""

    output_path: Path
    page_count: int


class StructuredDataToPDF:
    """Generate PDF documents from Pydantic model instances or dicts.

    Example:
        >>> from pydantic import BaseModel
        >>> class Invoice(BaseModel):
        ...     customer: str
        ...     amount: float
        >>> generator = StructuredDataToPDF(title="Lasku")
        >>> result = generator.run(Invoice(customer="Acme Oy", amount=100.0), "output.pdf")
    """

    def __init__(self, title: str = "Document") -> None:
        """Initialize the PDF generator.

        Args:
            title: Title shown at the top of the PDF document.
        """
        if FPDF is None:
            raise ImportError(
                "fpdf2 is required for PDF generation. "
                "Install with: pip install fpdf2"
            )
        self.title = title

    def run(self, data: BaseModel | dict | list, output_path: str | Path) -> PDFResult:
        """Generate a PDF from a Pydantic model instance or dict.

        Args:
            data: Pydantic model instance, dict, or list of dicts to render.
            output_path: Path where the PDF file will be saved.

        Returns:
            PDFResult with output path and page count.
        """
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Try to use a Unicode-capable font for Finnish characters
        self._setup_font(pdf)

        # Title
        pdf.set_font_size(16)
        pdf.cell(0, 10, self.title, ln=True, align="C")
        pdf.ln(8)

        # Render the data
        pdf.set_font_size(11)

        if isinstance(data, BaseModel):
            self._render_value(pdf, data.model_dump(), indent=0)
        elif isinstance(data, list):
            for i, item in enumerate(data, 1):
                self._write_line(pdf, f"Item {i}", indent=0, bold=True)
                if isinstance(item, BaseModel):
                    self._render_value(pdf, item.model_dump(), indent=1)
                elif isinstance(item, dict):
                    self._render_value(pdf, item, indent=1)
                else:
                    self._write_line(pdf, str(item), indent=1)
                pdf.ln(4)
        else:
            self._render_value(pdf, data, indent=0)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))

        return PDFResult(output_path=output_path, page_count=pdf.page_no())

    def _setup_font(self, pdf: FPDF) -> None:
        """Set up a Unicode-capable font for Finnish language support."""
        # Try common system fonts that support Finnish characters
        font_paths = [
            # Windows
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            # macOS
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]

        for font_path in font_paths:
            if Path(font_path).exists():
                try:
                    pdf.add_font("CustomFont", "", font_path)
                    pdf.set_font("CustomFont", size=11)
                    return
                except Exception:
                    continue

        # Fallback to built-in font (limited Unicode support)
        pdf.set_font("Helvetica", size=11)

    def _render_value(self, pdf: FPDF, value: Any, indent: int = 0) -> None:
        """Recursively render a value to the PDF.

        Args:
            pdf: FPDF instance to render to.
            value: Value to render (dict, list, or scalar).
            indent: Current indentation level.
        """
        if isinstance(value, dict):
            for key, val in value.items():
                label = self._format_key(key)
                if isinstance(val, dict):
                    # Nested object - show label, then recurse with indent
                    self._write_line(pdf, f"{label}:", indent)
                    self._render_value(pdf, val, indent + 1)
                elif isinstance(val, list):
                    # List - show label, then items
                    self._write_line(pdf, f"{label}:", indent)
                    self._render_list(pdf, val, indent + 1)
                else:
                    # Simple key-value pair
                    display_value = self._format_value(val)
                    self._write_line(pdf, f"{label}: {display_value}", indent)
        else:
            # Direct scalar value
            self._write_line(pdf, str(value), indent)

    def _render_list(self, pdf: FPDF, items: list, indent: int) -> None:
        """Render a list of items.

        Args:
            pdf: FPDF instance to render to.
            items: List of items to render.
            indent: Current indentation level.
        """
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                self._write_line(pdf, f"{i}.", indent)
                self._render_value(pdf, item, indent + 1)
            else:
                self._write_line(pdf, f"{i}. {item}", indent)

    def _write_line(self, pdf: FPDF, text: str, indent: int = 0, bold: bool = False) -> None:
        """Write a line of text to the PDF.

        Args:
            pdf: FPDF instance.
            text: Text to write.
            indent: Indentation level (in mm from left margin).
            bold: Whether to use bold font.
        """
        left_margin = 10 + (indent * 8)
        pdf.set_x(left_margin)
        pdf.multi_cell(0, 6, text.strip())

    @staticmethod
    def _format_key(key: str) -> str:
        """Format a field key for display.

        Args:
            key: The raw field name (e.g., 'customer_name').

        Returns:
            Formatted label (e.g., 'Customer Name').
        """
        return key.replace("_", " ").title()

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format a value for display.

        Args:
            value: The value to format.

        Returns:
            String representation of the value.
        """
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "Kyllä" if value else "Ei"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)
