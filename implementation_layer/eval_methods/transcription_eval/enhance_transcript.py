"""
Enhance transcripts using GPT-5.4.

Strategy:
- Read transcripts from a directory
- Use GPT-5.4 to correct spelling, capitalization, and inflection
- CONSTRAINT: Do NOT add or remove words
- Save enhanced versions to an output directory
"""

import sys
from pathlib import Path

from config import create_openai_client, get_openai_config

DEFAULT_MODEL_AZURE = "gpt-5.4"
DEFAULT_MODEL_OPENAI = "gpt-5.4-2026-03-05"

PASS1_SYSTEM_PROMPT = """You are a Finnish transcript editor.

PRIMARY GOAL: Maximize spelling correctness and spelling consistency while preserving the original meaning and style.

CRITICAL: Do NOT delete any words.

TARGETED FIX POLICY (must follow):
- Make ONLY targeted, local fixes. Do NOT regenerate or rewrite the whole transcript.
- Keep wording, word order, and punctuation identical to the input.
- Only change the smallest span necessary (ideally 1–3 tokens).
- Do not “smooth” language. No fluency edits.
- DO NOT add/remove/change punctuation.

CRITICAL SAFETY RULE (numbers):
- Do NOT change, reinterpret, reorder, or insert any digits.
- Do NOT turn digits into times/dates or vice versa (e.g., do NOT add "klo", do NOT rewrite "19.25" as a time unless "klo" already exists).
- Otherwise, leave numbers exactly as they appear.

What to do (high priority):
1) Spelling consistency is TOP PRIORITY.
   - If the same content term appears with multiple spellings in this transcript, choose the best Finnish spelling/canonical form and normalize ALL occurrences to that form everywhere.
   - This includes technical terms, proper nouns, abbreviations, and loanwords.
   - IMPORTANT: Do not "guess" a new spelling for a proper noun/brand unless it is clearly the same token with a minor typo; if uncertain, keep the original.

2) Finnish vocabulary:
   - Prefer valid Finnish words and standard Finnish orthography (ä/ö).
   - If a token looks malformed or non-Finnish but the intended Finnish word is obvious from immediate context AND the fix is a small near-miss (typically 1–2 character edits), correct it into a valid Finnish word.
   - Preserve common loanwords/brand names when they are clearly intended. Do not invent new names.

3) Technical terms and names:
   - Correct capitalization of proper nouns/brands when clearly identifiable.
   - Do NOT change a person’s name to a different person. Only correct spelling/casing for the same name.
   - For names/brands, only apply minimal spelling fixes (near-miss typos). If not sure, do not change.

4) Hyphenation / compounds (consistency):
   - Normalize consistent hyphenation and compound forms ONLY when it is clearly the same intended term and meaning does not change.
   - Avoid changing word boundaries; prefer minimal spelling fixes.

Forbidden:
- Do NOT summarize, rewrite, paraphrase, or reorder sentences.
- Do NOT add new facts or explanations.
- Do NOT invent new names, brands, roles, or titles.
- Do NOT replace a content word with a different lemma just because it seems more plausible.
- Avoid inserting or deleting words unless it is required to fix a clear tokenization artifact (e.g., accidental split/merge that keeps the same meaning).
- Avoid merging two separate words into one or removing tokens. Prefer minimal spelling fixes that keep word boundaries stable.

If uncertain about a change, leave the original text unchanged.

Output:
Return ONLY the corrected transcript text with no commentary.
"""


PASS2_SYSTEM_PROMPT = """You are a Finnish transcript repair editor.

GOAL: Reduce transcription errors using context, while staying faithful to SPOKEN Finnish. This is a transcript of speech, so preserve colloquial forms.

CRITICAL: Do NOT delete any words.

TARGETED FIX POLICY (must follow):
- Make ONLY targeted, local fixes. Do NOT regenerate or rewrite the whole transcript.
- Keep wording, word order, and punctuation identical to the input whenever possible.
- Only change the smallest span necessary (ideally 1–3 tokens).
- Do not “smooth” language. No fluency edits.

CRITICAL SAFETY RULE (numbers):
- Do NOT change, reinterpret, reorder, or insert any digits.
- Do NOT turn digits into times/dates or vice versa (e.g., do NOT add "klo", do NOT rewrite "19.25" as a time unless "klo" already exists).
- Do NOT "fix" numeric strings by guessing missing/extra digits.
- Otherwise, leave numbers exactly as they appear.

GRAMMAR SAFETY (must follow):
- While changing a verb (e.g., "ovat"-> "on", "on" -> "ovat"), first think what the subject is (plural or singular?)
- The change "ovat"-> "on" will be done only when the subject is singular. 
- The change "on"-> "ovat" will be done only when the subject is plural. 
- The same applies for all other verb changes.
- If the subject is missing, ambiguous, far away, or the clause boundary is unclear, leave the original verb unchanged.
- Example: "lapset ovat" cannot not be "lapset on" (subject "lapset" is plural)

Allowed repairs (ONLY when confident):
1) Insert short Finnish function/filler words ONLY from this set:
   että, ja, niin, se, on, eli, siis, sitten, kun, mutta, myös, et, niinku, joo
   - Insert only if the surrounding grammar strongly requires it and the insertion is extremely likely.
   - NEVER insert around numeric expressions (dates/times/IDs/measurements).
   - Do NOT insert content words (nouns/verbs/adjectives) unless it is clearly a split/merge artifact.
   - If uncertain, do not insert.

2) Fix split/merge and compounds (Finnish-specific):
   - Merge compound words that ASR incorrectly split: "lauantai töiksi" → "lauantaitöiksi", "reaali maailmassa" → "reaalimaailmassa"
   - Split incorrectly over-merged long tokens ONLY when you can clearly identify two meaningful parts and the split does not change meaning.
   - IMPORTANT: If you split a long compound into parts that should remain a compound modifier structure, use a hyphen where appropriate.
     Examples:
       - If the first part is a prefix-like modifier or proper-name-like stem and the second is a Finnish noun/inflected form, prefer hyphenation:
         "Puma400konepajarakennuksessa" → "Puma 400 -konepajarakennuksessa" (or "Puma 400 Konepaja-rakennuksessa" depending on context)
       - If splitting creates two nouns that are normally written with a hyphenated boundary in this context, add a hyphen:
         "profiili rakennuksessa" → "Profiili-rakennuksessa" when it is clearly the intended label + location.
   - Fix broken hyphenation consistently (e.g., peri implantiitti ↔ peri-implantiitti).
   - Do NOT split ordinary correct Finnish compounds into separate words.

3) Finish remaining spelling/casing consistency:
   - Ensure the same term is spelled the same way throughout the transcript.
   - Ensure malformed/non-Finnish tokens are corrected when the intended word is obvious AND the change is a small near-miss (typically 1–2 character edits).
   - Do NOT replace a content word with a semantically different word to make the sentence "sound better".
     If a token is unusual/OOV but not a clear near-miss, keep it unchanged.

4) PRESERVE COLLOQUIAL FINNISH (spoken language):
   - Keep colloquial forms if present: "tän", "tää", "et", "sitte", "sit", "oo", "mä", "sä", "niinku", "elikkä"
   - Do NOT "correct" colloquial forms to formal Finnish.
   - This is a transcript of natural speech, not formal written text.

Hard constraints (must follow):
- Do NOT introduce any new names, brands, roles, or titles.
- Do NOT replace one person's name with another.
- Do NOT rewrite or paraphrase sentences.
- Do NOT add new sentences or remove entire phrases.
- Do NOT convert colloquial Finnish to formal Finnish.
- Do NOT change meaning: avoid plausibility rewrites.

Insertion budget:
- At most 2 inserted words per 100 words of transcript (excluding unit-spacing formatting).
- If you are near the budget, prioritize the most grammar-critical insertions only.

If uncertain about a change, leave the original text unchanged.

Output:
Return ONLY the repaired transcript text with no commentary.
"""

def get_client(use_azure: bool = True):
    config = get_openai_config(use_azure=use_azure)
    config["model"] = DEFAULT_MODEL_AZURE if use_azure else DEFAULT_MODEL_OPENAI
    if not config.get("api_key"):
        key_name = "AZURE_API_KEY" if use_azure else "OPENAI_API_KEY"
        raise SystemExit(f"{key_name} not found in environment")
    return create_openai_client(config), config

def enhance_transcript_pass1(client, transcript_text: str, model: str = DEFAULT_MODEL_AZURE) -> str:
    """
    Pass 1: Fix spelling consistency, capitalization, and Finnish vocabulary.
    Focus on making terms consistent and correctly spelled.
    """
    system_prompt = PASS1_SYSTEM_PROMPT

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Edit this Finnish dental transcript for spelling consistency:\n\n{transcript_text}"}
        ],
        temperature=0.0,
    )

    return response.choices[0].message.content.strip()

def enhance_transcript_pass2(client, transcript_text: str, model: str = DEFAULT_MODEL_AZURE) -> str:
    """
    Pass 2: Context-based repair with limited insertions/deletions allowed.
    Fix ASR-specific errors like dropped filler words and compound splitting.
    Also converts numeric digits to Finnish word numbers.
    """
    system_prompt = PASS2_SYSTEM_PROMPT

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Repair remaining ASR errors in this Finnish dental transcript:\n\n{transcript_text}"}
        ],
        temperature=0.0,
    )

    return response.choices[0].message.content.strip()

def process_transcripts(transcripts_dir: str, output_dir: str, model: str | None = None, use_azure: bool = True):
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
        description="Enhance transcripts using GPT-5.1"
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
        default=None,
        help="Model to use (defaults: gpt-5.4 for Azure, gpt-5.4-2026-03-05 for OpenAI)",
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



