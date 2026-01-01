"""
PDF Generator for Työmaapäiväkirja (Construction Site Diary)

Generates PDF reports from extracted diary fields using ReportLab,
matching the Finnish construction diary template layout.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from typing import Dict, Any, Optional, List
from pathlib import Path
import base64

# Page size: A4 Portrait (210 × 297 mm = 595.28 × 841.89 points)
PAGE_WIDTH, PAGE_HEIGHT = A4  # A4 is already portrait orientation
MARGIN = 15 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)

# Styling constants
HEADER_LABEL_BG = colors.Color(0.77, 0.65, 0.46)  # #C4A574 tan/brown for header rows (Kohde, Sää, etc.)
MAIN_LABEL_BG = colors.Color(0.91, 0.87, 0.79)    # #E8DEC9 light brown/beige for main content labels
LIGHT_GRAY = colors.Color(0.93, 0.93, 0.93)       # #EDEDED light gray for main table labels
WHITE = colors.white
BLACK = colors.black

# Column widths for the main table
LABEL_COL_WIDTH = 120
VALUE_COL_WIDTH = CONTENT_WIDTH - LABEL_COL_WIDTH


def _get_value(data: Dict[str, Any], *keys: str, default: str = "") -> str:
    """Get value from dict, trying multiple key variations."""
    for key in keys:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                return ", ".join(str(v) for v in val if v)
            return str(val) if val else default
        # Try lowercase and with underscores
        key_lower = key.lower().replace(" ", "_").replace("-", "_")
        if key_lower in data:
            val = data[key_lower]
            if isinstance(val, list):
                return ", ".join(str(v) for v in val if v)
            return str(val) if val else default
    return default


def _create_styles() -> Dict[str, ParagraphStyle]:
    """Create paragraph styles for the PDF.

    Font specifications:
    - Title: Times-Bold, 12 pt
    - Table content: Times-Roman/Times-Bold, 9.6 pt
    """
    styles = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "DiaryTitle",
            parent=styles["Heading1"],
            fontName="Times-Bold",
            fontSize=12,  # 12 pt for title
            alignment=TA_RIGHT,
            spaceAfter=10,
        ),
        "label": ParagraphStyle(
            "FieldLabel",
            parent=styles["Normal"],
            fontName="Times-Bold",  # Bold for labels
            fontSize=9.6,  # 9.6 pt for table content
            alignment=TA_LEFT,
        ),
        "value": ParagraphStyle(
            "FieldValue",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=9.6,  # 9.6 pt for table content
            alignment=TA_LEFT,
        ),
        "header_label": ParagraphStyle(
            "HeaderLabel",
            parent=styles["Normal"],
            fontName="Times-Bold",  # Bold for labels
            fontSize=9.6,  # 9.6 pt for table content
            alignment=TA_LEFT,
        ),
    }


def _make_label_cell(text: str, styles: Dict) -> Paragraph:
    """Create a label cell paragraph."""
    return Paragraph(f"<b>{text}</b>", styles["label"])


def _make_value_cell(text: str, styles: Dict) -> Paragraph:
    """Create a value cell paragraph."""
    return Paragraph(text or "", styles["value"])


def _format_resurssit_henkilosto(value: str, styles: Dict) -> Table:
    """Format resurssit_henkilosto field with Henkilöstö header and 2-column table layout.

    Expected format: "Työnjohtajat: X hlö, Työntekijät: X hlö, Alihankkijat: X hlö, Yhteensä: X hlö"
    Output:
        Henkilöstö
        Työnjohtajat: X hlö    Työntekijät: X hlö
        Alihankkijat: X hlö    Yhteensä: X hlö (bold)

    The table continues for as many values as there are (2 columns per row).
    Entries starting with 'yhteensä' are displayed in bold.
    """
    if not value:
        return Paragraph("", styles["value"])

    # Parse the comma-separated values
    parts = [p.strip() for p in value.split(",") if p.strip()]

    if len(parts) == 0:
        return Paragraph(value, styles["value"])

    # Create the header row
    header = Paragraph("<b>Henkilöstö</b>", styles["value"])

    # Helper to format a part (bold if starts with 'yhteensä')
    def format_part(part: str) -> Paragraph:
        if part.lower().startswith("yhteensä"):
            return Paragraph(f"<b>{part}</b>", styles["value"])
        return Paragraph(part, styles["value"])

    # Create 2-column grid for all values
    grid_data = []
    for i in range(0, len(parts), 2):
        row = [format_part(parts[i])]
        if i + 1 < len(parts):
            row.append(format_part(parts[i + 1]))
        else:
            row.append(Paragraph("", styles["value"]))  # Empty cell for odd number
        grid_data.append(row)

    # If only one part, still create a row
    if len(grid_data) == 0:
        grid_data.append([format_part(parts[0]), Paragraph("", styles["value"])])

    # Create inner grid table
    col_width = (VALUE_COL_WIDTH - 20) / 2
    grid_table = Table(grid_data, colWidths=[col_width, col_width])
    grid_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # Combine header and grid
    content_table = Table(
        [[header], [grid_table]],
        colWidths=[VALUE_COL_WIDTH - 10]
    )
    content_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    return content_table


def _format_multiline_list(value: str, styles: Dict) -> Paragraph:
    """Format a comma-separated value as multiple lines.

    Each comma-separated item appears on a new line.
    """
    if not value:
        return Paragraph("", styles["value"])

    # Split by comma and join with line breaks
    parts = [p.strip() for p in value.split(",") if p.strip()]
    formatted = "<br/>".join(parts)
    return Paragraph(formatted, styles["value"])


def _decode_base64_image(base64_str: str) -> BytesIO:
    """Decode a base64 image string to BytesIO."""
    # Remove data URL prefix if present (e.g., "data:image/png;base64,")
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    image_data = base64.b64decode(base64_str)
    return BytesIO(image_data)


def _build_image_grid(images: List[str], max_cols: int = 5) -> Table:
    """Build a grid of thumbnail images."""
    THUMB_SIZE = 60  # Size for each thumbnail

    image_objects = []
    for img_b64 in images:
        try:
            img_buffer = _decode_base64_image(img_b64)
            img = Image(img_buffer, width=THUMB_SIZE, height=THUMB_SIZE)
            image_objects.append(img)
        except Exception:
            # Skip invalid images
            continue

    if not image_objects:
        return None

    # Arrange images in rows
    rows = []
    current_row = []
    for img in image_objects:
        current_row.append(img)
        if len(current_row) == max_cols:
            rows.append(current_row)
            current_row = []
    if current_row:
        # Pad the last row with empty strings
        while len(current_row) < max_cols:
            current_row.append("")
        rows.append(current_row)

    col_width = THUMB_SIZE + 4
    grid_table = Table(rows, colWidths=[col_width] * max_cols)
    grid_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return grid_table


def _build_header_table(
    data: Dict[str, Any],
    styles: Dict,
    logo_path: Optional[str] = None
) -> Table:
    """Build the header section with logo and title."""
    # Logo placeholder or actual logo
    if logo_path and Path(logo_path).exists():
        # Lotus Demolition logo - wider horizontal format
        logo = Image(logo_path, width=140, height=35)
    else:
        logo = Paragraph("<b>LOGO</b>", styles["label"])

    title = Paragraph("<b>TYÖMAAPÄIVÄKIRJA</b>", styles["title"])

    header_data = [[logo, title]]
    header_table = Table(
        header_data,
        colWidths=[CONTENT_WIDTH * 0.5, CONTENT_WIDTH * 0.5]
    )
    header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return header_table


def _build_info_table(data: Dict[str, Any], styles: Dict) -> Table:
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

    # Column widths: first column matches main table's LABEL_COL_WIDTH
    # Fourth column reduced by half, second column increased by same amount
    remaining_width = CONTENT_WIDTH - LABEL_COL_WIDTH
    fourth_col_width = remaining_width * 0.165  # Half of original 0.33
    extra_width = remaining_width * 0.165       # Added to second column
    col_widths = [
        LABEL_COL_WIDTH,                        # Kohde/Sää label - same as main table
        remaining_width * 0.50 + extra_width,   # Kohde/Sää value (wider)
        remaining_width * 0.17,                 # Laatija/Päivämäärä label
        fourth_col_width,                       # Laatija/Päivämäärä value (narrower)
    ]
    info_table = Table(info_data, colWidths=col_widths)
    # All columns white background
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return info_table


def _build_main_table(
    data: Dict[str, Any],
    styles: Dict,
    images: Optional[List[str]] = None,
    field_specs: Optional[List] = None
) -> Table:
    """Build the main content table with all diary fields dynamically.

    This function now dynamically iterates through all fields in the extraction data,
    matching the same behavior as the UI which displays all extracted fields.
    """

    # Fields that are handled in the info table (first two rows) or signature table
    HEADER_FIELDS = {"kohde", "laatija", "sää", "saa", "päivämäärä", "paivamaara"}
    SIGNATURE_FIELDS = {"valvojan_allekirjoitus", "vastaavan_allekirjoitus"}

    def normalize_key(key: str) -> str:
        """Normalize a field key for comparison."""
        return key.lower().replace(" ", "_").replace("-", "_")

    def get_display_label(key: str) -> str:
        """Get a display-friendly label from a field key."""
        # Replace underscores with spaces and capitalize
        return key.replace("_", " ").title()

    # Determine which fields to display and their order
    if field_specs:
        # Use field_specs order if provided (same as UI)
        fields_to_display = []
        for field in field_specs:
            field_name = field if isinstance(field, str) else field.get("field_name", "")
            if not field_name:
                continue
            normalized = normalize_key(field_name)
            if normalized in HEADER_FIELDS or normalized in SIGNATURE_FIELDS:
                continue
            label = (
                get_display_label(field_name)
                if isinstance(field, str)
                else field.get("label") or get_display_label(field_name)
            )
            fields_to_display.append({"name": field_name, "label": label})
    else:
        # Fall back to extraction_data keys
        fields_to_display = [
            {"name": key, "label": get_display_label(key)}
            for key in data.keys()
            if normalize_key(key) not in HEADER_FIELDS
            and normalize_key(key) not in SIGNATURE_FIELDS
        ]

    table_data = []
    for field in fields_to_display:
        field_name = field["name"]
        # Get value from data
        value = data.get(field_name, "")
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v)
        elif value is not None:
            value = str(value)
        else:
            value = ""

        # Normalize field name for special handling
        normalized_field = normalize_key(field_name)
        is_liitteet = normalized_field == "liitteet"
        is_resurssit = normalized_field in ("resurssit_henkilosto", "resurssit_henkilöstö", "resurssit")
        is_paivan_tyot = normalized_field in ("paivan_tyot_omat_tyot", "päivän_työt_omat_työt", "päivän_työt", "paivan_tyot")

        # Use the provided label or fallback to generated label
        label = field.get("label") or get_display_label(field_name)

        # Special handling for Liitteet row with images
        if is_liitteet and images and len(images) > 0:
            # Create content with count and image grid
            image_grid = _build_image_grid(images)
            if image_grid:
                # Combine count text and image grid
                count_text = f"{len(images)} kuvaa"
                content = Table(
                    [[Paragraph(count_text, styles["value"])], [image_grid]],
                    colWidths=[VALUE_COL_WIDTH - 10]
                )
                content.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]))
                table_data.append([
                    _make_label_cell(label, styles),
                    content,
                ])
            else:
                table_data.append([
                    _make_label_cell(label, styles),
                    _make_value_cell(value or f"{len(images)} kuvaa", styles),
                ])
        # Special handling for resurssit_henkilosto - 2x2 table format
        elif is_resurssit and value:
            content = _format_resurssit_henkilosto(value, styles)
            table_data.append([
                _make_label_cell(label, styles),
                content,
            ])
        # Special handling for paivan_tyot_omat_tyot - each item on new line
        elif is_paivan_tyot and value:
            content = _format_multiline_list(value, styles)
            table_data.append([
                _make_label_cell(label, styles),
                content,
            ])
        else:
            table_data.append([
                _make_label_cell(label, styles),
                _make_value_cell(value, styles),
            ])

    # If no fields found, add a placeholder row
    if not table_data:
        table_data.append([
            _make_label_cell("Ei kenttiä", styles),
            _make_value_cell("Ei tietoja", styles),
        ])

    main_table = Table(
        table_data,
        colWidths=[LABEL_COL_WIDTH, VALUE_COL_WIDTH]
    )

    # Apply styling
    style_commands = [
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    # Apply light gray background color to all label cells (first column)
    for i in range(len(table_data)):
        style_commands.append(("BACKGROUND", (0, i), (0, i), LIGHT_GRAY))
        style_commands.append(("BACKGROUND", (1, i), (1, i), WHITE))

    main_table.setStyle(TableStyle(style_commands))
    return main_table


def _build_signature_table(data: Dict[str, Any], styles: Dict) -> Table:
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
    sig_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("BACKGROUND", (1, 0), (1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 1, BLACK),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),  # Extra space for signature
    ]))
    return sig_table


def generate_diary_pdf(
    extraction_data: Dict[str, Any],
    logo_path: Optional[str] = None,
    title: str = "TYÖMAAPÄIVÄKIRJA",
    images: Optional[List[str]] = None,
    field_specs: Optional[List] = None,
) -> BytesIO:
    """
    Generate a PDF report from extracted diary fields.

    Args:
        extraction_data: Dictionary of extracted field values
        logo_path: Optional path to company logo image
        title: Title for the document
        images: Optional list of base64-encoded images for attachments
        field_specs: Optional list of field specifications (for ordering/filtering)

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
    elements: List = []

    # Header with logo and title
    header_table = _build_header_table(extraction_data, styles, logo_path)
    elements.append(header_table)
    elements.append(Spacer(1, 5 * mm))

    # Info section (Kohde, Laatija, Sää, Päivämäärä)
    info_table = _build_info_table(extraction_data, styles)
    elements.append(info_table)
    elements.append(Spacer(1, 2 * mm))

    # Main content table - now uses dynamic field rendering
    main_table = _build_main_table(extraction_data, styles, images, field_specs)
    elements.append(main_table)
    elements.append(Spacer(1, 2 * mm))

    # Signature section
    sig_table = _build_signature_table(extraction_data, styles)
    elements.append(sig_table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
