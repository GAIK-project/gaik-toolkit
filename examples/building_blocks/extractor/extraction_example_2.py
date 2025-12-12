"""
End-to-end example:
- Parse each whole PDF with a parser
- Classify the parsed document (Purchase order vs Bill of material)
- Prepend a header and save per-file outputs
- Also build a combined output with --- separators
"""

import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.building_blocks.extractor import DataExtractor, SchemaGenerator, get_openai_config
from gaik.building_blocks.parsers import VisionParser

try:
    # Optional imports; only needed if classify_document() constructs its own client
    from openai import AzureOpenAI, OpenAI
except Exception:
    OpenAI = None
    AzureOpenAI = None


def _make_llm_client(cfg: dict):
    """
    Create an OpenAI (or Azure OpenAI) client + return (client, model, use_azure).
    Uses deterministic settings later in classify_document().
    """
    use_azure = cfg.get("use_azure", True)

    if use_azure:
        if AzureOpenAI is None:
            raise RuntimeError("AzureOpenAI SDK not available. Please install `openai` >= 1.0")
        client = AzureOpenAI(
            api_key=cfg["api_key"],
            api_version=cfg["api_version"],
            azure_endpoint=cfg["azure_endpoint"].split("/openai/")[0],  # robust to full path input
        )
        model = cfg.get("model", "gpt-4.1")
    else:
        if OpenAI is None:
            raise RuntimeError("OpenAI SDK not available. Please install `openai` >= 1.0")
        client = OpenAI(api_key=cfg["api_key"])
        model = cfg.get("model", "gpt-4.1-2025-04-14")

    return client, model, use_azure


def classify_document(
    markdown_text: str,
    client,
    model: str,
    use_azure: bool,
) -> str:
    """
    Classify a fully parsed document as either:
      - 'Purchase order'
      - 'Bill of material'

    Returns the **formatted header** string, e.g. "**Purchase order:**"
    Deterministic: temperature=0, top_p=1
    """
    system_msg = (
        "You are a precise document classifier. "
        "Given the FULL parsed content of a single document, respond with exactly one of:\n"
        "- Purchase order\n"
        "- Bill of material\n"
        "No extra words."
    )

    # Keep prompt short and deterministic
    user_msg = (
        "Classify the following parsed document:\n\n"
        f"{markdown_text[:500]}"  # safety cap; classification should not need more
    )

    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        top_p=1.0,
        max_completion_tokens=50,
    )

    if use_azure:
        resp = client.chat.completions.create(**kwargs)
        label = resp.choices[0].message.content.strip().lower()
    else:
        resp = client.chat.completions.create(**kwargs)
        label = resp.choices[0].message.content.strip().lower()

    if "purchase" in label:
        return "**Purchase order:**"
    # Default to Bill of material if it's not clearly PO
    return "**Bill of material:**"


def main():
    # 1) OpenAI/Azure configuration
    config = get_openai_config(use_azure=True)  # set False to use non-Azure OpenAI
    custom_prompt = ""  # Optional extra parsing instructions

    # 2) Initialize VisionParser (uses PyMuPDF for PDF to image conversion)
    print("\nCreating Parser...")
    parser = VisionParser(
        openai_config=config,  # Required
        custom_prompt=custom_prompt,  # Optional
        use_context=True,  # Improves multi-page continuity
    )
    # Note: dpi and clean_output are passed to convert_pdf() method

    # parser = PyMuPDFParser()
    # Parse document with markdown format (simple text)

    print("OK Parser initialized")

    # 3) PDFs to process
    pdf_paths = [
        "input/PO.pdf",
        "input/BOM1.pdf",
        "input/BOM2.pdf",
        "input/BOM3.pdf",
    ]

    # 4) Optional: build a combined output too
    combined_output_parts = []

    # Prepare LLM client for classification (reuse the same config)
    client, model, use_azure = _make_llm_client(config)

    for path in pdf_paths:
        path = str(Path(path))  # normalize
        print(f"\nParsing PDF: {path}")

        # 4a) Parse the full document
        # VisionParser.convert_pdf() returns a list of strings (one per page or merged)
        markdown_pages = parser.convert_pdf(path, dpi=150, clean_output=True)

        if not markdown_pages or not isinstance(markdown_pages, list):
            raise RuntimeError(f"Invalid parse result for: {path}")

        # With clean_output=True, it returns a list with one merged string
        full_markdown = markdown_pages[0] if len(markdown_pages) == 1 else "".join(markdown_pages)
        if not full_markdown.strip():
            raise RuntimeError(f"Empty parse result for: {path}")

        # 4b) Classify the WHOLE parsed document
        header = classify_document(full_markdown, client, model, use_azure)

        # 4c) Prepend header + separator
        final_markdown = f"{header}\n{full_markdown}\n---\n"

        # 4d) Save per-file output next to the input (..._output.md)
        out_file = Path(path).with_suffix("").as_posix() + "_output.md"
        print(f"Saving: {out_file}")
        parser.save_markdown(final_markdown, out_file)

        # 4e) Append to combined output
        combined_output_parts.append(final_markdown)
    # 5) Save combined output, if desired
    combined = "".join(combined_output_parts)
    combined_path = "./combined_classified_output.md"
    print(f"\nSaving combined output: {combined_path}")
    with open(combined_path, "w", encoding="utf-8") as f:
        f.write(combined)
    print("OK All done!")

    return combined_path


def extract_po_bom_data(combined_file_path: str = "./combined_classified_output.md"):
    """
    Extract and match PO+BOM data from the combined classified output.

    Uses SchemaGenerator to automatically:
    1. Detect nested structure
    2. Generate appropriate Pydantic models
    3. Extract and match all PO items with BOM data
    4. Save results to JSON and CSV
    """

    print("\n" + "=" * 80)
    print("PO+BOM DATA EXTRACTION")
    print("=" * 80)

    # Define extraction requirements
    user_requirements = """
    The task is to extract key fields from customer documents (Purchase Order (PO) and Bill of Material (BOM),
    and align them so that each PO item is enriched with the correct technical details.
    Begin with the customer's purchase order, which may include multiple items.
    The item is linked to its BOM via a Material Number. For every item in the PO,
    extract the Material Number along with the basic item details, such as Quantity, Description,
    and Delivery Date. Use the item's Material Number from the PO to find the BOM having the same Material Number (represented as 'ID').
    From the matching BOM, extract the part's 'Type/Part Designation' and Dimensions.
    The final output should contain as many lines as the number of items in the PO.
    Each line should have:
    - Material Number
    - Quantity
    - Description
    - Delivery Date (from PO)
    - Type/Part Designation
    - Dimensions (from BOM).
    **IMPORTANT**: There could be multiple items in the PO (hence multiple Material Numbers). For each Material Number,
    the above mentioned fields have to be extracted and matched with the corresponding BOM.
    """

    # Read the combined file
    try:
        with open(combined_file_path, encoding="utf-8") as f:
            combined_content = f.read()
        print(f"\nOK Loaded document from: {combined_file_path}")
        print(f"  Content length: {len(combined_content)} characters\n")
    except FileNotFoundError:
        print(f"\nX Error: File not found: {combined_file_path}")
        print("Please run the main() function first to generate the combined file.")
        return None

    config = get_openai_config(use_azure=True)  # Set to False for standard OpenAI

    # Step 1: Generate schema
    generator = SchemaGenerator(config=config)
    schema = generator.generate_schema(user_requirements=user_requirements)

    print(f"\nOK Generated schema: {schema.__name__}")
    print(f"  Structure: {generator.structure_analysis.structure_type}")

    # Step 2: Extract data
    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=schema,
        requirements=generator.item_requirements,
        user_requirements=user_requirements,
        documents=[combined_content],
        save_json=True,
        json_path="po_bom_extraction_results.json",
    )

    # Display results summary
    print("\n" + "=" * 80)
    print("EXTRACTION RESULTS SUMMARY")
    print("=" * 80)

    for i, result in enumerate(results, 1):
        print(f"\nDocument {i}:")
        for key, value in result.items():
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                print(f"  {key}: {len(value)} items extracted")
                # Show first item as example
                print("\n  Example item:")
                for item_key, item_val in value[0].items():
                    print(f"    {item_key}: {item_val}")
                if len(value) > 1:
                    print(f"\n  ... and {len(value) - 1} more items")
            else:
                print(f"  {key}: {value}")

    print("\n" + "=" * 80)
    print("OK PO+BOM extraction complete!")
    print("=" * 80)

    return results


if __name__ == "__main__":
    try:
        # Step 1: Parse PDFs and create combined classified output
        combined_path = main()

        # Step 2: Extract PO+BOM data from combined output
        print("\n\n")
        extract_po_bom_data(combined_path)

    except Exception as e:
        print(f"\nX Error: {e}")
        import traceback

        traceback.print_exc()


