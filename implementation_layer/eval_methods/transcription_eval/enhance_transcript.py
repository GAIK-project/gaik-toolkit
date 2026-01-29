"""
Enhance transcripts using GPT-5.1 with dental-focused Finnish dictionary.

Strategy:
- Read transcripts from a directory
- Use GPT-5.1 to correct spelling, capitalization, and inflection
- CONSTRAINT: Do NOT add or remove words
- Save enhanced versions to an output directory
"""

import sys
from pathlib import Path

from config import create_openai_client, get_openai_config

# Dental-focused Finnish dictionary
DENTAL_DICTIONARY = {
    # Brands
    "straumann": "Straumann",
    "strauman": "Straumann",
    "nobel biocare": "Nobel Biocare",
    "nobel": "Nobel Biocare",
    "dentsply sirona": "Dentsply Sirona",
    "dentsply": "Dentsply Sirona",
    "splacirona": "Dentsply Sirona",
    "densply sirona": "Dentsply Sirona",
    "neodent": "Neodent",
    "niden": "Neodent",
    "camlog": "Camlog",
    "camlog-conelog": "Camlog-Conelog",
    "implantona": "Implantona",
    "implanttoona": "Implantona",

    # Finnish dental terms
    "implantti": "implantti",
    "implantit": "implantit",
    "implanttiprotetiikka": "implanttiprotetiikka",
    "implanttihoito": "implanttihoito",
    "peri-implantiitti": "peri-implantiitti",
    "periimplantiitti": "peri-implantiitti",
    "esteettinen": "esteettinen",
    "esteettisyys": "esteettisyys",
    "estettinen": "esteettinen",
    "hammaslääkäri": "hammaslääkäri",
    "parodontologi": "parodontologi",
    "hammashoito": "hammashoito",
    "protetiikka": "protetiikka",
    "krooni": "krooni",
    "kruunu": "kruunu",
    "silta": "silta",
    "pohjustus": "pohjustus",
    "täyte": "täyte",
    "juurenhoito": "juurenhoito",
    "kirurgia": "kirurgia",
    "kirurginen": "kirurginen",
    "osteotomia": "osteotomia",
    "sinuslift": "sinuslift",
    "augmentaatio": "augmentaatio",
    "luunsiirto": "luunsiirto",

    # Names
    "timo suojärvi": "Timo Suojärvi",
    "virpi myller": "Virpi Myller",
    "ilkka pallonen": "Ilkka Pallonen",
    "martta martola": "Martta Martola",
    "martta martoon": "Martta Martola",
    "peeter": "Peeter",
    "peetteri": "Peeter",

    # Company suffixes
    "oy": "Oy",
    "ab": "Ab",

    # Locations
    "clarion": "Clarion",
    "helsinki": "Helsinki",
}

##Focuses on spelling corrections

PASS1_SYSTEM_PROMPT = """You are a Finnish transcript editor specialized in dental webinar transcripts (implantology, prosthetics, periodontology).

PRIMARY GOAL: Maximize spelling correctness and spelling consistency while preserving the original meaning and style.

What to do (high priority):
1) Spelling consistency is TOP PRIORITY.
   - If the same content term appears with multiple spellings in this transcript, choose the best Finnish spelling/canonical form and normalize ALL occurrences to that form everywhere.
   - This includes dental terms, anatomy, procedures, materials, abbreviations, and loanwords used in dental context.

2) Finnish vocabulary:
   - Prefer valid Finnish words and standard Finnish orthography.
   - If a token looks malformed or non-Finnish but the intended Finnish word is obvious from immediate context, correct it into a valid Finnish word.
   - Preserve common dental loanwords/brand names when they are clearly intended.

3) Technical terms and names:
   - Use the DICTIONARY as strong guidance for correct spellings and capitalization.
   - Correct capitalization of proper nouns/brands when clearly identifiable.
   - Do NOT change a person’s name to a different person. Only correct spelling/casing for the same name (or dictionary-mapped variant).

4) Hyphenation / compounds (consistency):
   - Normalize consistent hyphenation and compound forms (e.g., periimplantiitti → peri-implantiitti) when it is clearly the same intended term.
   - Normalize common compound dental terms consistently across the transcript.

Forbidden:
- Do NOT summarize, rewrite, paraphrase, or reorder sentences.
- Do NOT add new facts or explanations.
- Do NOT invent new names, brands, roles, or titles.
- Avoid inserting or deleting words unless it is required to fix a clear tokenization artifact (e.g., accidental split/merge that keeps the same meaning).
- Avoid merging two separate words into one or removing tokens. Prefer minimal spelling fixes that keep word boundaries stable.

DICTIONARY (use as reference for correct spellings and capitalization):
{dictionary}

Output:
Return ONLY the corrected transcript text with no commentary.
"""

## Focuses on context based repair
PASS2_SYSTEM_PROMPT = """You are a Finnish transcript repair editor specialized in dental webinar transcripts.

GOAL: Reduce transcription errors using context, while staying faithful to SPOKEN Finnish. This is a transcript of speech, so preserve colloquial forms.

Allowed repairs (ONLY when confident):
1) Insert short Finnish function/filler words ONLY from this set:
   että, ja, niin, se, on, eli, siis, sitten, kun, mutta, myös, et, niinku, joo
   - Insert only if the surrounding grammar strongly requires it and the insertion is extremely likely.
   - Do NOT insert content words (nouns/verbs/adjectives) unless it is clearly a split/merge artifact.

2) Fix split/merge and compounds:
   - Merge compound words that ASR incorrectly split: "lauantai töiksi" → "lauantaitöiksi", "reaali maailmassa" → "reaalimaailmassa"
   - Fix broken hyphenation consistently (e.g., peri implantiitti ↔ peri-implantiitti).
   - Fix malformed loanwords/terms consistently, but do not invent new terms.

3) Finish remaining spelling/casing consistency:
   - Ensure the same term is spelled the same way throughout the transcript.
   - Ensure malformed/non-Finnish tokens are corrected when the intended word is obvious from immediate context.

4) Convert numeric digits to Finnish word numbers WITH CORRECT INFLECTION:
   CRITICAL: Use correct Finnish grammatical case for numbers!
   - Genitive case (possessive): "20 prosentin" → "kahdenkymmenen prosentin" (NOT "kaksikymmenen")
   - Nominative: "20 prosenttia" → "kaksikymmentä prosenttia"
   - Common genitive forms: yhden, kahden, kolmen, neljän, viiden, kuuden, seitsemän, kahdeksan, yhdeksän, kymmenen
   - "11" genitive → "yhdentoista", "20" genitive → "kahdenkymmenen", "55" genitive → "viidenkymmenenviiden"
   - Decimals: "37,5" → "kolmekymmentäseitsemän ja puoli"
   - Years/decades: "70-luvulta" → "seitsemänkymmentäluvulta"
   - Keep numbers in proper nouns/codes unchanged (e.g., "COVID-19", "ISO 9001")

5) PRESERVE COLLOQUIAL FINNISH (spoken language):
   - Keep colloquial forms if present: "tän", "tää", "et", "sitte", "sit", "oo", "mä", "sä", "niinku", "elikkä"
   - Do NOT "correct" colloquial forms to formal Finnish
   - This is a transcript of natural speech, not formal written text

Hard constraints (must follow):
- Do NOT delete any words in Pass 2 (number conversion may change word count).
- Do NOT introduce any new names, brands, roles, or titles.
- Do NOT replace one person's name with another (unless explicitly dictionary-mapped).
- Do NOT rewrite or paraphrase sentences.
- Do NOT add new sentences or remove entire phrases.
- Do NOT convert colloquial Finnish to formal Finnish.

Insertion budget:
- At most 4 inserted words per 100 words of transcript (excluding number conversions).
- If you are near the budget, prioritize the most grammar-critical insertions only.

DICTIONARY (strong guidance for spellings/capitalization):
{dictionary}

If uncertain about a change, leave the original text unchanged.

Output:
Return ONLY the repaired transcript text with no commentary.
"""

def get_client(use_azure: bool = True):
    config = get_openai_config(use_azure=use_azure)
    if not config.get("api_key"):
        key_name = "AZURE_API_KEY" if use_azure else "OPENAI_API_KEY"
        raise SystemExit(f"{key_name} not found in environment")
    return create_openai_client(config), config

def format_dictionary_for_prompt(dictionary: dict) -> str:
    """Format dictionary as readable list for prompt"""
    entries = []
    for wrong, correct in sorted(dictionary.items()):
        if wrong.lower() != correct.lower():
            entries.append(f'  "{wrong}" → "{correct}"')
    return "\n".join(entries)  

def enhance_transcript_pass1(client, transcript_text: str, model: str = "gpt-5.1") -> str:
    """
    Pass 1: Fix spelling consistency, capitalization, and Finnish vocabulary.
    Focus on making terms consistent and correctly spelled.
    """
    dictionary_text = format_dictionary_for_prompt(DENTAL_DICTIONARY)
    system_prompt = PASS1_SYSTEM_PROMPT.format(dictionary=dictionary_text)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Edit this Finnish dental transcript for spelling consistency:\n\n{transcript_text}"}
        ],
        temperature=0.0,
    )

    return response.choices[0].message.content.strip()

def enhance_transcript_pass2(client, transcript_text: str, model: str = "gpt-5.1") -> str:
    """
    Pass 2: Context-based repair with limited insertions/deletions allowed.
    Fix ASR-specific errors like dropped filler words and compound splitting.
    Also converts numeric digits to Finnish word numbers.
    """
    dictionary_text = format_dictionary_for_prompt(DENTAL_DICTIONARY)
    system_prompt = PASS2_SYSTEM_PROMPT.format(dictionary=dictionary_text)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Repair remaining ASR errors in this Finnish dental transcript:\n\n{transcript_text}"}
        ],
        temperature=0.0,
    )

    return response.choices[0].message.content.strip()

def process_transcripts(transcripts_dir: str, output_dir: str, model: str = "gpt-5.1", use_azure: bool = True):
    """Process all transcripts in directory

    Args:
        transcripts_dir: Directory containing original transcripts
        output_dir: Directory to save enhanced transcripts
        model: Model to use for enhancement
        use_azure: Whether to use Azure OpenAI
    """
    transcripts_path = Path(transcripts_dir)
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    if not transcripts_path.exists():
        raise FileNotFoundError(f"Transcripts directory not found: {transcripts_path}")

    client, config = get_client(use_azure=use_azure)
    model = model or config["model"]
    transcript_files = sorted(transcripts_path.glob("*.txt"))

    if not transcript_files:
        print(f"No .txt files found in {transcripts_path}")
        return

    print(f"Found {len(transcript_files)} transcripts to enhance")
    print(f"Model: {model}")
    print()

    for transcript_file in transcript_files:
        print(f"Processing: {transcript_file.name}")

        # Read original transcript
        original_text = transcript_file.read_text(encoding="utf-8")
        original_word_count = len(original_text.split())
        print(f"  Original: {original_word_count} words")

        # Pass 1: Spelling consistency + Finnish vocabulary
        print(f"  Pass 1: Spelling consistency...")
        pass1_text = enhance_transcript_pass1(client, original_text, model=model)
        pass1_word_count = len(pass1_text.split())
        print(f"    -> {pass1_word_count} words (delta: {pass1_word_count - original_word_count:+d})")

        # Pass 2: Context-based repair + number conversion
        print(f"  Pass 2: Context repair + number conversion...")
        pass2_text = enhance_transcript_pass2(client, pass1_text, model=model)
        pass2_word_count = len(pass2_text.split())
        print(f"    -> {pass2_word_count} words (delta: {pass2_word_count - pass1_word_count:+d})")

        # Final result
        enhanced_text = pass2_text
        print(f"  Total change: {original_word_count} -> {pass2_word_count} words ({pass2_word_count - original_word_count:+d})")

        # Save enhanced transcript
        output_file = output_path / transcript_file.name
        output_file.write_text(enhanced_text, encoding="utf-8")
        print(f"  Saved to: {output_file}")
        print()

    print(f"Done! Enhanced transcripts saved to: {output_path}")

def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Enhance transcripts using GPT-5.1 with dental dictionary"
    )
    ap.add_argument(
        "--transcripts-dir",
        type=str,
        default="transcripts",
        help="Directory containing original transcripts (default: transcripts)",
    )
    ap.add_argument(
        "--output-dir",
        type=str,
        default="enhanced",
        help="Directory to save enhanced transcripts (default: enhanced)",
    )
    ap.add_argument(
        "--model",
        type=str,
        default="gpt-5.1",
        help="Model to use (default: gpt-5.1)",
    )

    args = ap.parse_args()

    process_transcripts(
        args.transcripts_dir,
        args.output_dir,
        args.model,
        use_azure=True
    )

if __name__ == "__main__":
    main()



