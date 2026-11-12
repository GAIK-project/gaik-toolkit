"""Operations example: parse, build a schema, extract with evidence, classify, and async use.

Every step calls one function of ``gaik.operations`` on a short synthetic service note.

    python operations_example.py

Needs: pip install "gaik[operations]" and model credentials (.env). The provider is the one
``LLM_PROVIDER`` names (Azure OpenAI by default).
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from gaik.operations import (  # noqa: E402
    FieldDefinition,
    OperationSettings,
    build_schema,
    classify_text,
    extract_fields,
    parse_document,
    run_async,
)

SERVICE_NOTE = """Service note

The visit took place on 14 March 2026 at the Kallio pumping station.
Technician Aino Virtanen replaced the shaft seal of pump P-12 and checked two valves.
Water had been dripping from the seal onto the motor housing.
The pump was back in use the same afternoon.
"""

FIELDS = [
    FieldDefinition(name="Käyntipäivä", type="date", label="Visit date"),
    FieldDefinition(name="site", description="The place where the work was done"),
    FieldDefinition(name="technician", description="The person who did the work"),
    FieldDefinition(name="valves_checked", type="int", description="Number of valves checked"),
    FieldDefinition(name="pump_in_use", type="bool", description="Was the pump returned to use?"),
    FieldDefinition(name="supervisor", description="The supervisor, if the note names one"),
]

# One settings object for every call. The defaults are a 120 s timeout per model request,
# gaik's prints kept out of stdout, and the provider from LLM_PROVIDER.
SETTINGS = OperationSettings()


def parse_example() -> str:
    """Read a text file. A PDF or a DOCX is read the same way; no model call is made."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "service_note.txt"
        path.write_text(SERVICE_NOTE, encoding="utf-8")
        document = parse_document(path)
    print(f"Parsed a {document.kind} file: {len(document.pages)} page, {len(document.text)} chars")
    return document.text


def schema_example() -> None:
    """The schema is built from the definitions: no model call, and no file to load."""
    schema = build_schema(FIELDS)
    print("\nSchema fields and the names they map back to:")
    for safe_name, name in schema.names.items():
        print(f"  {safe_name:<16} <- {name}")


def print_values(values) -> None:
    for item in values:
        quote = f'"{item.evidence}"' if item.evidence else "-"
        print(f"  {item.label:<16} {item.value!s:<26} {item.verdict or '-':<10} {quote}")


def extract_example(text: str) -> None:
    """One model call. Each value comes with its quote, checked against the text."""
    values = extract_fields(text, FIELDS, settings=SETTINGS)
    print("\nExtracted fields (label, value, verdict, quote):")
    print_values(values)


def classify_example(text: str) -> None:
    """One label, with the model's own estimate of each label's probability."""
    result = classify_text(
        text,
        {
            "urgent": "A risk to people or equipment that needs action today",
            "normal": "Work that is done or can wait for the next planned visit",
        },
        settings=SETTINGS,
    )
    print(f"\nClassified as {result.label} ({result.confidence:.0%}): {result.probabilities}")


async def async_example(text: str) -> None:
    """From async code: the same function in a worker thread, with a deadline in seconds."""
    values = await run_async(extract_fields, text, FIELDS, settings=SETTINGS, deadline=240)
    print("\nThe same extraction through run_async:")
    print_values(values)


def main() -> None:
    text = parse_example()
    schema_example()
    extract_example(text)
    classify_example(text)
    asyncio.run(async_example(text))


if __name__ == "__main__":
    main()
