import json
from pathlib import Path

from openai import OpenAI

# We want these info from LLM
FIELDS = [
    "Raportin tyyppi",
    "Tarkkailijan nimi",
    "Tarkkailijaorganisaatio",
    "Tarkkailija on kesätyöntekijä",
    "Tapahtuma-aika",
    "Sijaintitiedot",
    "Kuva",
    "Tapahtuma oli vakava",
    "Tapahtuma-alueen kuvaus",
    "Mahdolliset seuraukset",
    "Toteutetut toimenpiteet",
    "Ehdotus",
]


def extract_fields_from_text(file_path: Path,client: OpenAI,model_name: str):

    #LLM should return JSON format
    text = file_path.read_text(encoding="utf-8")
    prompt = f"""
    You are a strict JSON generator.
    Return ONLY a valid JSON object with these exact keys:
    {FIELDS}
    
    Rules:
    - If a field is missing, use "--tyhjä"
    - Do NOT invent information
    - "Raportin tyyppi": one of "Turvallisuus", "Ympäristönsuojelu", "Energiatehokkuus"
    - "Tapahtuma oli vakava": "Kyllä" if serious, otherwise "Ei"
    
    Text:
    \"\"\"
    {text}
    \"\"\"
    """

    try:
        response = client.responses.create(
            model=model_name,
            input=prompt,
            max_output_tokens=1000
        )

        raw_reply = response.output_text.strip()

        # cleaning for better JSON format  if required
        start = raw_reply.find("{")
        end = raw_reply.rfind("}")

        if start == -1 or end == -1:
            print(f"!No JSON found in {file_path.name}")
            return {}

        json_text = raw_reply[start:end + 1]

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            print(f"!Malformed JSON in {file_path.name}")
            data = {}

        # Ensure all fields exist
        for field in FIELDS:
            if field not in data or data[field] is None:
                data[field] = "--tyhjä"

        return data

    except Exception as e:
        print(f"!Error extracting from {file_path.name}: {e}")
        return None


def run_field_extraction(input_dir:Path, output_dir: Path, model_name: str, api_key: str):

    output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    text_files = sorted(input_dir.glob("*.txt"))

    for txt_path in text_files:
        output_path = output_dir / f"{txt_path.stem}_form.json"
        print(f"Processing {txt_path.name} ...")
        extracted = extract_fields_from_text(
            file_path=txt_path,
            client=client,
            model_name=model_name
        )

        if extracted is None:
            output_path.write_text("{}", encoding="utf-8")
            print(f"!Saved empty JSON for {txt_path.name}")
            continue

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        print(f"!Saved JSON: {output_path.name}")
