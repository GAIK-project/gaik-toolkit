"""Transcriber router - Audio/video transcription endpoints"""

import os
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

try:
    from utils import validate_file_size
except ImportError:
    from api.utils import validate_file_size
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter()

# PASS1_SYSTEM_PROMPT = """You are a Finnish transcript editor.

# PRIMARY GOAL: Maximize spelling correctness and spelling consistency while preserving the original meaning and style.

# What to do (high priority):
# 1) Spelling consistency is TOP PRIORITY.
#    - If the same content term appears with multiple spellings in this transcript, choose the best Finnish spelling/canonical form and normalize ALL occurrences to that form everywhere.
#    - This includes technical terms, proper nouns, abbreviations, and loanwords.

# 2) Finnish vocabulary:
#    - Prefer valid Finnish words and standard Finnish orthography.
#    - If a token looks malformed or non-Finnish but the intended Finnish word is obvious from immediate context, correct it into a valid Finnish word.
#    - Preserve common loanwords/brand names when they are clearly intended.

# 3) Technical terms and names:
#    - Correct capitalization of proper nouns/brands when clearly identifiable.
#    - Do NOT change a person’s name to a different person. Only correct spelling/casing for the same name.
#    - Do not change dates, time, and other numbers

# 4) Hyphenation / compounds (consistency):
#    - Normalize consistent hyphenation and compound forms when it is clearly the same intended term.
#    - Normalize common compound terms consistently across the transcript.

# Forbidden:
# - Do NOT summarize, rewrite, paraphrase, or reorder sentences.
# - Do NOT add new facts or explanations.
# - Do NOT invent new names, brands, roles, or titles.
# - Avoid inserting or deleting words unless it is required to fix a clear tokenization artifact (e.g., accidental split/merge that keeps the same meaning).
# - Avoid merging two separate words into one or removing tokens. Prefer minimal spelling fixes that keep word boundaries stable.

# Output:
# Return ONLY the corrected transcript text with no commentary.
# """

# ## Focuses on context based repair
# PASS2_SYSTEM_PROMPT = """You are a Finnish transcript repair editor.

# GOAL: Reduce transcription errors using context, while staying faithful to SPOKEN Finnish. This is a transcript of speech, so preserve colloquial forms.

# Allowed repairs (ONLY when confident):
# 1) Insert short Finnish function/filler words ONLY from this set:
#    että, ja, niin, se, on, eli, siis, sitten, kun, mutta, myös, et, niinku, joo
#    - Insert only if the surrounding grammar strongly requires it and the insertion is extremely likely.
#    - Do NOT insert content words (nouns/verbs/adjectives) unless it is clearly a split/merge artifact.

# 2) Fix split/merge and compounds:
#    - Merge compound words that ASR incorrectly split: "lauantai töiksi" → "lauantaitöiksi", "reaali maailmassa" → "reaalimaailmassa"
#    - Fix broken hyphenation consistently (e.g., peri implantiitti ↔ peri-implantiitti).
#    - Fix malformed loanwords/terms consistently, but do not invent new terms.

# 3) Finish remaining spelling/casing consistency:
#    - Ensure the same term is spelled the same way throughout the transcript.
#    - Ensure malformed/non-Finnish tokens are corrected when the intended word is obvious from immediate context.
# 4) Convert numeric digits to Finnish word numbers WITH CORRECT INFLECTION:
#    CRITICAL: Use correct Finnish grammatical case for numbers!
#    - Genitive case (possessive): "20 prosentin" → "kahdenkymmenen prosentin" (NOT "kaksikymmenen")
#    - Nominative: "20 prosenttia" → "kaksikymmentä prosenttia"
#    - Common genitive forms: yhden, kahden, kolmen, neljän, viiden, kuuden, seitsemän, kahdeksan, yhdeksän, kymmenen
#    - "11" genitive → "yhdentoista", "20" genitive → "kahdenkymmenen", "55" genitive → "viidenkymmenenviiden"
#    - Decimals: "37,5" → "kolmekymmentäseitsemän ja puoli"
#    - Years/decades: "70-luvulta" → "seitsemänkymmentäluvulta"
#    - Keep numbers in proper nouns/codes unchanged (e.g., "COVID-19", "ISO 9001")
#    - Keep date and time exactly in the same format (DO NOT change)
# 5) PRESERVE COLLOQUIAL FINNISH (spoken language):
#    - Keep colloquial forms if present: "tän", "tää", "et", "sitte", "sit", "oo", "mä", "sä", "niinku", "elikkä"
#    - Do NOT "correct" colloquial forms to formal Finnish
#    - This is a transcript of natural speech, not formal written text

# Hard constraints (must follow):
# - Do NOT delete any words in Pass 2 (number conversion may change word count).
# - Do NOT introduce any new names, brands, roles, or titles.
# - Do NOT replace one person's name with another.
# - Do NOT rewrite or paraphrase sentences.
# - Do NOT add new sentences or remove entire phrases.
# - Do NOT convert colloquial Finnish to formal Finnish.

# Insertion budget:
# - At most 4 inserted words per 100 words of transcript (excluding number conversions).
# - If you are near the budget, prioritize the most grammar-critical insertions only.

# If uncertain about a change, leave the original text unchanged.

# Output:
# Return ONLY the repaired transcript text with no commentary.
# """

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


class TranscriptSegment(BaseModel):
    start: float | None = None
    end: float | None = None
    speaker: str | None = None
    text: str | None = None


class CorrectionSummary(BaseModel):
    total_changes: int
    insertions: int
    deletions: int
    substitutions: int


class DiffChunk(BaseModel):
    kind: str
    original: str = ""
    corrected: str = ""


class TranscribeResponse(BaseModel):
    filename: str
    raw_transcript: str
    enhanced_transcript: str | None
    corrected_transcript: str | None = None
    correction_summary: CorrectionSummary | None = None
    diff_chunks: list[DiffChunk] | None = None
    job_id: str
    segments: list[TranscriptSegment] | None = None


@router.post("", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    custom_context: str = Form(""),
    enhanced: bool = Form(False),
    compress_audio: bool = Form(True),
    language: str = Form("auto"),
    diarization: bool = Form(False),
    speaker_count: int | None = Form(None),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
    initial_prompt: str | None = Form(None),
    prefer_local_first: bool = Form(True),
    fix_transcription_errors: bool = Form(False),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if enhanced and fix_transcription_errors:
        raise HTTPException(
            status_code=400,
            detail="Polished text and fix transcription errors cannot be enabled at the same time",
        )

    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Either AZURE_API_KEY or OPENAI_API_KEY environment variable must be set",
        )

    suffix = Path(file.filename).suffix.lower()
    supported = [".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac"]
    if suffix not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(supported)}",
        )

    content = await validate_file_size(file)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from gaik.software_components.config import create_openai_client
        from gaik.software_components.transcriber import Transcriber, get_openai_config

        config = get_openai_config(use_azure=use_azure)
        local_api_base = os.getenv("LOCAL_TRANSCRIBER_API_BASE")
        local_api_key = os.getenv("LOCAL_TRANSCRIBER_API_KEY")

        transcriber_kwargs = {
            "api_config": config,
            "output_dir": tempfile.gettempdir(),
            "enhanced_transcript": enhanced,
            "compress_audio": compress_audio,
            "language": language,
            "diarization": diarization,
            "speaker_count": speaker_count,
            "min_speakers": min_speakers,
            "max_speakers": max_speakers,
            "initial_prompt": initial_prompt,
            "local_api_base": local_api_base,
            "local_api_key": local_api_key,
        }

        if prefer_local_first and local_api_base and local_api_key:
            try:
                transcriber = Transcriber(
                    **transcriber_kwargs,
                    transcription_model="whisper_local",
                )
                result = transcriber.transcribe(file_path=tmp_path, custom_context=custom_context)
            except Exception as exc:
                print(f"Local transcription failed: {exc}")
                print("Falling back to configured transcription model.")
                transcriber = Transcriber(**transcriber_kwargs)
                result = transcriber.transcribe(file_path=tmp_path, custom_context=custom_context)
        else:
            if prefer_local_first and not (local_api_base and local_api_key):
                print(
                    "prefer_local_first=True but local_api_base/local_api_key are not configured; "
                    "using configured transcription model instead."
                )
            transcriber = Transcriber(**transcriber_kwargs)
            result = transcriber.transcribe(file_path=tmp_path, custom_context=custom_context)

        corrected_transcript = None
        correction_summary = None
        diff_chunks = None
        if fix_transcription_errors:
            client = create_openai_client(config)
            corrected_transcript = _enhance_transcript_pass1(
                client, result.raw_transcript, config["model"]
            )
            corrected_transcript = _enhance_transcript_pass2(
                client, corrected_transcript, config["model"]
            )
            correction_summary = _summarize_corrections(result.raw_transcript, corrected_transcript)
            diff_chunks = _build_diff_chunks(result.raw_transcript, corrected_transcript)

        return TranscribeResponse(
            filename=file.filename,
            raw_transcript=result.raw_transcript,
            enhanced_transcript=result.enhanced_transcript,
            corrected_transcript=corrected_transcript,
            correction_summary=correction_summary,
            diff_chunks=diff_chunks,
            job_id=result.job_id,
            segments=result.segments if diarization else None,
        )
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Transcriber not installed: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _extract_response_text(response, fallback_text: str) -> str:
    if not response or not getattr(response, "choices", None):
        return fallback_text

    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None) if message is not None else None

    if isinstance(content, str):
        stripped = content.strip()
        if stripped:
            return stripped
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text_part = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if isinstance(text_part, str) and text_part.strip():
                parts.append(text_part.strip())
        if parts:
            return "\n".join(parts)

    return fallback_text


def _enhance_transcript_pass1(client, transcript_text: str, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PASS1_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Edit this Finnish transcript for spelling consistency:\n\n{transcript_text}",
            },
        ],
        temperature=0.0,
    )
    return _extract_response_text(response, transcript_text)


def _enhance_transcript_pass2(client, transcript_text: str, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PASS2_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Repair remaining ASR errors in this Finnish transcript:\n\n{transcript_text}",
            },
        ],
        temperature=0.0,
    )
    return _extract_response_text(response, transcript_text)


def _summarize_corrections(original_text: str, corrected_text: str) -> CorrectionSummary:
    original_tokens = original_text.split()
    corrected_tokens = corrected_text.split()
    matcher = SequenceMatcher(a=original_tokens, b=corrected_tokens)

    insertions = 0
    deletions = 0
    substitutions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            insertions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "replace":
            a_len = i2 - i1
            b_len = j2 - j1
            substitutions += min(a_len, b_len)
            if b_len > a_len:
                insertions += b_len - a_len
            elif a_len > b_len:
                deletions += a_len - b_len

    return CorrectionSummary(
        total_changes=insertions + deletions + substitutions,
        insertions=insertions,
        deletions=deletions,
        substitutions=substitutions,
    )


def _build_diff_chunks(original_text: str, corrected_text: str) -> list[DiffChunk]:
    original_tokens = original_text.split()
    corrected_tokens = corrected_text.split()
    matcher = SequenceMatcher(a=original_tokens, b=corrected_tokens)
    chunks: list[DiffChunk] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        chunks.append(
            DiffChunk(
                kind=tag,
                original=" ".join(original_tokens[i1:i2]),
                corrected=" ".join(corrected_tokens[j1:j2]),
            )
        )

    return chunks
