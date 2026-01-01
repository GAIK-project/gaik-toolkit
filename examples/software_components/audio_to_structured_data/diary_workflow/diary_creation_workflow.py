"""
Example: extracts key structured fields from construction site audios by dynamically building extraction models from user requiements and creates a construction site diary
Workflow name: audio_to_structured_data
Workflow: input audio->transcribe->parse user requirement and build schema->extract key data
"""

from __future__ import annotations
import json
import sys
import base64
from pathlib import Path
from dotenv import load_dotenv
from pdf_generator import generate_diary_pdf
load_dotenv(Path(__file__).parent.parent.parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))
from gaik.software_components.audio_to_structured_data import AudioToStructuredData  



def create_pdf_report(extracted_fields: list[dict]) -> Path | None:
    """
    Build a diary PDF using the first extracted record, optional logo, and any images in ./images.
    Returns the path to the saved PDF or None on failure.
    """
    pdf_output = Path(__file__).parent / "diary.pdf"
    assets_dir = Path(__file__).parent / "assets"
    logo_path = assets_dir / "lod.png"
    images_dir = Path(__file__).parent / "images"
    images_b64: list[str] = []
    if images_dir.exists():
        for img_path in images_dir.iterdir():
            if img_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                try:
                    images_b64.append(base64.b64encode(img_path.read_bytes()).decode("utf-8"))
                except OSError:
                    pass
    try:
        first_record = extracted_fields[0] if extracted_fields else {}
        pdf_buffer = generate_diary_pdf(
            extraction_data=first_record,
            logo_path=str(logo_path) if logo_path.exists() else None,
            images=images_b64 or None,
        )
        pdf_output.write_bytes(pdf_buffer.getvalue())
        print(f"Diary PDF saved to: {pdf_output}")
        return pdf_output
    except Exception as exc:
        print(f"Failed to generate PDF: {exc}")
        return None

USER_REQUIREMENTS = """
    The task is to extract all the required fields needed for the official Työmaapäiväkirja (daily construction site diary) 
    from the transcript of an audio recorded by a construction site supervisor who verbally describes the day's events on the 
    worksite.
    Output MUST follow the field structure below exactly, using Finnish field names.
    If the transcript does not mention a field, return an empty string ("").
    All the extracted fields should be as brief as possible, not exeeding a few key words.

    Fields to Extract (in Finnish)
    Extract the following fields exactly as they appear below. The structure reflects the diary template on the uploaded page:
    1. Kohde [Subject of the diary]
    2. Laatija [Name of the author recording the diary]
    3. Sää [e.g., 3 °C, 2 m/s, 78 % suht. kosteus, Kp: -1.4 C]
    4. Päivämäärä [Format: dd.mm.yyyy]
    5. Resurssit - Henkilöstö [e.g., Työnjohtajat: 2 hlö, Työntekijät: 1 hlö, Alihankkijat: 4 hlö, Yhteensä: 7 hlö]
    6. Työviikko [Week number, e.g., 2]
    7. Päivän työt (Omat työt) [List all works, e.g., sisäpurku, rungon purku, sähköjen ja veden katkaisu]
    8. Päivän tapahtumat [e.g., Ei tapahtumia]
    9. Liitteet [number of attachments, e.g., 4 photos, 1 email attachment, 1 note, etc.]
    10. Valvojan huomiot
    11. Päivän poikkeamat
    12. Aloitetut työvaiheet
    13. Käynnissä olevat työvai [e.g., Sisäpurku, Rungon purku, Lajittelu, Työmaan aitaus]
    14. Päättyneet työvai [e.g., Asbestipurku]
    15. Keskeytyneet työvai [e.g., Rungon purku]
    16. Pyydetyt lisäajat
    17. Tehdyt katselmukset
    18. Valvojan huomautukset
    19. Valvojan allekirjoitus
    20. Vastaavan allekirjoitus
"""

def main() -> None:
    extract_options = {"generate_schema": False}
    generate_schema = extract_options.pop("generate_schema", True) 
    schema_name = extract_options.pop("schema_name", "schema") 

    pipeline = AudioToStructuredData(use_azure=True)

    existing = None if generate_schema else pipeline.load_schema(Path(__file__).parent / "schema", schema_name)
    schema = requirements = None
    if existing:
        schema, requirements = existing

    result = pipeline.run(
        file_path=Path(r"diary.mp3"),
        user_requirements=USER_REQUIREMENTS,
        extract_options=extract_options,
        schema=schema,
        requirements=requirements,
    )

    if result.schema and result.requirements and generate_schema:
        pipeline.save_schema(result.schema, result.requirements, Path(__file__).parent / "schema", schema_name)

    create_pdf_report(result.extracted_fields)

if __name__ == "__main__":
    main()
