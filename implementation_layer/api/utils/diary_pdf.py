"""
PDF Generator for Työmaapäiväkirja (Construction Site Diary)

Generates PDF reports from extracted diary fields using ReportLab,
matching the Finnish construction diary template layout.
"""

from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Page size: A4 Portrait (210 × 297 mm = 595.28 × 841.89 points)
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 15 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)

# Styling constants
LIGHT_GRAY = colors.Color(0.93, 0.93, 0.93)
WHITE = colors.white
BLACK = colors.black

# Column widths for the main table
LABEL_COL_WIDTH = 120
VALUE_COL_WIDTH = CONTENT_WIDTH - LABEL_COL_WIDTH


def _get_value(data: dict[str, Any], *keys: str, default: str = "") -> str:
    """Get value from dict, trying multiple key variations."""
    for key in keys:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                return ", ".join(str(v) for v in val if v)
            return str(val) if val else default
        key_lower = key.lower().replace(" ", "_").replace("-", "_")
        if key_lower in data:
            val = data[key_lower]
            if isinstance(val, list):
                return ", ".join(str(v) for v in val if v)
            return str(val) if val else default
    return default


def _create_styles() -> dict[str, ParagraphStyle]:
    """Create paragraph styles for the PDF."""
    styles = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "DiaryTitle",
            parent=styles["Heading1"],
            fontName="Times-Bold",
            fontSize=12,
            alignment=TA_RIGHT,
            spaceAfter=10,
        ),
        "label": ParagraphStyle(
            "FieldLabel",
            parent=styles["Normal"],
            fontName="Times-Bold",
            fontSize=9.6,
            alignment=TA_LEFT,
        ),
        "value": ParagraphStyle(
            "FieldValue",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=9.6,
            alignment=TA_LEFT,
        ),
    }


def _make_label_cell(text: str, styles: dict) -> Paragraph:
    """Create a label cell paragraph."""
    return Paragraph(f"<b>{text}</b>", styles["label"])


def _make_value_cell(text: str, styles: dict) -> Paragraph:
    """Create a value cell paragraph."""
    return Paragraph(text or "", styles["value"])


def _format_resurssit_henkilosto(value: str, styles: dict) -> Table:
    """Format resurssit_henkilosto field with 2-column table layout."""
    if not value:
        return Paragraph("", styles["value"])

    parts = [p.strip() for p in value.split(",") if p.strip()]

    if len(parts) == 0:
        return Paragraph(value, styles["value"])

    header = Paragraph("<b>Henkilöstö</b>", styles["value"])

    def format_part(part: str) -> Paragraph:
        if part.lower().startswith("yhteensä"):
            return Paragraph(f"<b>{part}</b>", styles["value"])
        return Paragraph(part, styles["value"])

    grid_data = []
    for i in range(0, len(parts), 2):
        row = [format_part(parts[i])]
        if i + 1 < len(parts):
            row.append(format_part(parts[i + 1]))
        else:
            row.append(Paragraph("", styles["value"]))
        grid_data.append(row)

    if len(grid_data) == 0:
        grid_data.append([format_part(parts[0]), Paragraph("", styles["value"])])

    col_width = (VALUE_COL_WIDTH - 20) / 2
    grid_table = Table(grid_data, colWidths=[col_width, col_width])
    grid_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    content_table = Table([[header], [grid_table]], colWidths=[VALUE_COL_WIDTH - 10])
    content_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    return content_table


def _format_multiline_list(value: str, styles: dict) -> Paragraph:
    """Format a comma-separated value as multiple lines."""
    if not value:
        return Paragraph("", styles["value"])

    parts = [p.strip() for p in value.split(",") if p.strip()]
    formatted = "<br/>".join(parts)
    return Paragraph(formatted, styles["value"])


def _build_header_table(
    data: dict[str, Any], styles: dict, logo_path: str | None = None
) -> Table:
    """Build the header section with logo and title."""
    if logo_path and Path(logo_path).exists():
        logo = Image(logo_path, width=140, height=35)
    else:
        logo = Paragraph("<b>LOGO</b>", styles["label"])

    title = Paragraph("<b>TYÖMAAPÄIVÄKIRJA</b>", styles["title"])

    header_data = [[logo, title]]
    header_table = Table(header_data, colWidths=[CONTENT_WIDTH * 0.5, CONTENT_WIDTH * 0.5])
    header_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return header_table


def _build_info_table(data: dict[str, Any], styles: dict) -> Table:
    """Build the info section (Kohde/Laatija, Sää/Päivämäärä)."""
    kohde = _get_value(data, "kohde", "Kohde")
    laatija = _get_value(data, "laatija", "Laatija")
    saa = _get_value(data, "sää", "saa", "Sää")
    paivamaara = _get_value(data, "päivämäärä", "paivamaara", "Päivämäärä")

    info_data = [
        [
            _make_label_cell("Kohde", styles),
            _make_value_cell(kohde, styles),
            _make_label_cell("Laatija", styles),
            _make_value_cell(laatija, styles),
        ],
        [
            _make_label_cell("Sää", styles),
            _make_value_cell(saa, styles),
            _make_label_cell("Päivämäärä", styles),
            _make_value_cell(paivamaara, styles),
        ],
    ]

    remaining_width = CONTENT_WIDTH - LABEL_COL_WIDTH
    fourth_col_width = remaining_width * 0.165
    extra_width = remaining_width * 0.165
    col_widths = [
        LABEL_COL_WIDTH,
        remaining_width * 0.50 + extra_width,
        remaining_width * 0.17,
        fourth_col_width,
    ]
    info_table = Table(info_data, colWidths=col_widths)
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 1, BLACK),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BLACK),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return info_table


def _build_main_table(data: dict[str, Any], styles: dict) -> Table:
    """Build the main content table with all diary fields dynamically."""

    HEADER_FIELDS = {"kohde", "laatija", "sää", "saa", "päivämäärä", "paivamaara"}
    SIGNATURE_FIELDS = {"valvojan_allekirjoitus", "vastaavan_allekirjoitus"}

    def normalize_key(key: str) -> str:
        return key.lower().replace(" ", "_").replace("-", "_")

    def get_display_label(key: str) -> str:
        return key.replace("_", " ").title()

    fields_to_display = [
        {"name": key, "label": get_display_label(key)}
        for key in data.keys()
        if normalize_key(key) not in HEADER_FIELDS
        and normalize_key(key) not in SIGNATURE_FIELDS
    ]

    table_data = []
    for field in fields_to_display:
        field_name = field["name"]
        value = data.get(field_name, "")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v)
        elif value is not None:
            value = str(value)
        else:
            value = ""

        normalized_field = normalize_key(field_name)
        is_resurssit = normalized_field in (
            "resurssit_henkilosto",
            "resurssit_henkilöstö",
            "resurssit",
        )
        is_paivan_tyot = normalized_field in (
            "paivan_tyot_omat_tyot",
            "päivän_työt_omat_työt",
            "päivän_työt",
            "paivan_tyot",
        )

        label = field.get("label") or get_display_label(field_name)

        if is_resurssit and value:
            content = _format_resurssit_henkilosto(value, styles)
            table_data.append([_make_label_cell(label, styles), content])
        elif is_paivan_tyot and value:
            content = _format_multiline_list(value, styles)
            table_data.append([_make_label_cell(label, styles), content])
        else:
            table_data.append(
                [_make_label_cell(label, styles), _make_value_cell(value, styles)]
            )

    if not table_data:
        table_data.append(
            [_make_label_cell("Ei kenttiä", styles), _make_value_cell("Ei tietoja", styles)]
        )

    main_table = Table(table_data, colWidths=[LABEL_COL_WIDTH, VALUE_COL_WIDTH])

    style_commands = [
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    for i in range(len(table_data)):
        style_commands.append(("BACKGROUND", (0, i), (0, i), LIGHT_GRAY))
        style_commands.append(("BACKGROUND", (1, i), (1, i), WHITE))

    main_table.setStyle(TableStyle(style_commands))
    return main_table


def _build_signature_table(data: dict[str, Any], styles: dict) -> Table:
    """Build the signature section."""
    valvojan_allekirjoitus = _get_value(
        data, "valvojan_allekirjoitus", "Valvojan allekirjoitus"
    )
    vastaavan_allekirjoitus = _get_value(
        data, "vastaavan_allekirjoitus", "Vastaavan allekirjoitus"
    )

    sig_data = [
        [
            _make_label_cell("Valvojan allekirjoit", styles),
            _make_value_cell(valvojan_allekirjoitus, styles),
        ],
        [
            _make_label_cell("Vastaavan allekirjoi", styles),
            _make_value_cell(vastaavan_allekirjoitus, styles),
        ],
    ]

    sig_table = Table(sig_data, colWidths=[LABEL_COL_WIDTH, VALUE_COL_WIDTH])
    sig_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
                ("BACKGROUND", (1, 0), (1, -1), WHITE),
                ("BOX", (0, 0), (-1, -1), 1, BLACK),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BLACK),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
            ]
        )
    )
    return sig_table


def generate_diary_pdf(
    extraction_data: dict[str, Any],
    logo_path: str | None = None,
) -> BytesIO:
    """
    Generate a PDF report from extracted diary fields.

    Args:
        extraction_data: Dictionary of extracted field values
        logo_path: Optional path to company logo image

    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )

    styles = _create_styles()
    elements: list = []

    header_table = _build_header_table(extraction_data, styles, logo_path)
    elements.append(header_table)
    elements.append(Spacer(1, 5 * mm))

    info_table = _build_info_table(extraction_data, styles)
    elements.append(info_table)
    elements.append(Spacer(1, 2 * mm))

    main_table = _build_main_table(extraction_data, styles)
    elements.append(main_table)
    elements.append(Spacer(1, 2 * mm))

    sig_table = _build_signature_table(extraction_data, styles)
    elements.append(sig_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer
