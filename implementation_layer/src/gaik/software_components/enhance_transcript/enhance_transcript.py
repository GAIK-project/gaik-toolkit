"""Two-pass transcript enhancement for Finnish ASR output."""

from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel

from gaik.software_components.config import create_openai_client, get_openai_config

DEFAULT_MODEL_AZURE = "gpt-5.4"
DEFAULT_MODEL_OPENAI = "gpt-5.4-2026-03-05"

PASS1_SYSTEM_PROMPT = """You are a Finnish transcript editor.

PRIMARY GOAL: Maximize spelling correctness and spelling consistency while preserving the original meaning and style.

CRITICAL: Do NOT delete any words.

TARGETED FIX POLICY (must follow):
- Make ONLY targeted, local fixes. Do NOT regenerate or rewrite the whole transcript.
- Keep wording, word order, and punctuation identical to the input.
- Only change the smallest span necessary (ideally 1-3 tokens).
- Do not smooth language. No fluency edits.
- Do NOT add, remove, or change punctuation.

CRITICAL SAFETY RULE (numbers):
- Do NOT change, reinterpret, reorder, or insert any digits.
- Do NOT turn digits into times or dates, or vice versa.
- Otherwise, leave numbers exactly as they appear.

What to do (high priority):
1) Spelling consistency is TOP PRIORITY.
   - If the same content term appears with multiple spellings in this transcript, choose the best Finnish spelling or canonical form and normalize ALL occurrences to that form everywhere.
   - This includes technical terms, proper nouns, abbreviations, and loanwords.
   - IMPORTANT: Do not guess a new spelling for a proper noun or brand unless it is clearly the same token with a minor typo. If uncertain, keep the original.

2) Finnish vocabulary:
   - Prefer valid Finnish words and standard Finnish orthography.
   - If a token looks malformed or non-Finnish but the intended Finnish word is obvious from immediate context AND the fix is a small near-miss, correct it into a valid Finnish word.
   - Preserve common loanwords and brand names when they are clearly intended. Do not invent new names.

3) Technical terms and names:
   - Correct capitalization of proper nouns and brands when clearly identifiable.
   - Do NOT change a person's name to a different person. Only correct spelling or casing for the same name.
   - For names and brands, only apply minimal spelling fixes. If not sure, do not change.

4) Hyphenation and compounds:
   - Normalize consistent hyphenation and compound forms ONLY when it is clearly the same intended term and meaning does not change.
   - Avoid changing word boundaries. Prefer minimal spelling fixes.

Forbidden:
- Do NOT summarize, rewrite, paraphrase, or reorder sentences.
- Do NOT add new facts or explanations.
- Do NOT invent new names, brands, roles, or titles.
- Do NOT replace a content word with a different lemma just because it seems more plausible.
- Avoid inserting or deleting words unless it is required to fix a clear tokenization artifact that keeps the same meaning.
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
- Only change the smallest span necessary (ideally 1-3 tokens).
- Do not smooth language. No fluency edits.

CRITICAL SAFETY RULE (numbers):
- Do NOT change, reinterpret, reorder, or insert any digits.
- Do NOT turn digits into times or dates, or vice versa.
- Do NOT fix numeric strings by guessing missing or extra digits.
- Otherwise, leave numbers exactly as they appear.

GRAMMAR SAFETY (must follow):
- While changing a verb, first think what the subject is: singular or plural.
- Change verbs only when the subject agreement is clear.
- If the subject is missing, ambiguous, far away, or the clause boundary is unclear, leave the original verb unchanged.

Allowed repairs (ONLY when confident):
1) Insert short Finnish function or filler words ONLY from this set:
   etta, ja, niin, se, on, eli, siis, sitten, kun, mutta, myos, et, niinku, joo
   - Insert only if the surrounding grammar strongly requires it and the insertion is extremely likely.
   - NEVER insert around numeric expressions.
   - Do NOT insert content words unless it is clearly a split or merge artifact.
   - If uncertain, do not insert.

2) Fix split, merge, and compound issues:
   - Merge compound words that ASR incorrectly split.
   - Split incorrectly over-merged long tokens ONLY when you can clearly identify two meaningful parts and the split does not change meaning.
   - Use a hyphen where appropriate for Finnish compound modifier structures.
   - Fix broken hyphenation consistently.
   - Do NOT split ordinary correct Finnish compounds into separate words.

3) Finish remaining spelling and casing consistency:
   - Ensure the same term is spelled the same way throughout the transcript.
   - Ensure malformed or non-Finnish tokens are corrected when the intended word is obvious AND the change is a small near-miss.
   - Do NOT replace a content word with a semantically different word just to make the sentence sound better.

4) PRESERVE COLLOQUIAL FINNISH:
   - Keep colloquial forms if present, such as tan, taa, et, sitte, sit, oo, ma, sa, niinku, elikka.
   - Do NOT correct colloquial forms to formal Finnish.
   - This is a transcript of natural speech, not formal written text.

Hard constraints (must follow):
- Do NOT introduce any new names, brands, roles, or titles.
- Do NOT replace one person's name with another.
- Do NOT rewrite or paraphrase sentences.
- Do NOT add new sentences or remove entire phrases.
- Do NOT convert colloquial Finnish to formal Finnish.
- Do NOT change meaning.

Insertion budget:
- At most 2 inserted words per 100 words of transcript.
- If you are near the budget, prioritize the most grammar-critical insertions only.

If uncertain about a change, leave the original text unchanged.

Output:
Return ONLY the repaired transcript text with no commentary.
"""


class CorrectionSummary(BaseModel):
    total_changes: int
    insertions: int
    deletions: int
    substitutions: int


class DiffChunk(BaseModel):
    kind: str
    original: str = ""
    corrected: str = ""


class TranscriptEnhancerResult(BaseModel):
    original_text: str
    enhanced_text: str
    source_file: str | None = None
    correction_summary: CorrectionSummary | None = None
    diff_chunks: list[DiffChunk] | None = None


class TranscriptEnhancer:
    """Enhance Finnish transcripts using a two-pass prompt workflow."""

    def __init__(
        self,
        api_config: dict | None = None,
        *,
        use_azure: bool = True,
        model: str | None = None,
    ) -> None:
        config = dict(api_config) if api_config is not None else get_openai_config(use_azure=use_azure)
        config["model"] = model or self._default_model_for_config(config)
        if not config.get("api_key"):
            key_name = "AZURE_API_KEY" if config.get("use_azure", False) else "OPENAI_API_KEY"
            raise ValueError(f"{key_name} not found in environment or api_config")

        self.api_config = config
        self.model = config["model"]
        self.client = create_openai_client(config)

    def enhance_text(
        self,
        transcript_text: str,
        *,
        generate_summary: bool = False,
        diff_chunks: bool = False,
    ) -> TranscriptEnhancerResult:
        transcript_text = transcript_text.strip()
        if not transcript_text:
            raise ValueError("transcript_text must not be empty")

        pass1_text = self._enhance_pass1(transcript_text)
        enhanced_text = self._enhance_pass2(pass1_text)

        return TranscriptEnhancerResult(
            original_text=transcript_text,
            enhanced_text=enhanced_text,
            correction_summary=(
                self._summarize_corrections(transcript_text, enhanced_text) if generate_summary else None
            ),
            diff_chunks=self._build_diff_chunks(transcript_text, enhanced_text) if diff_chunks else None,
        )

    def enhance_file(
        self,
        file_path: str | Path,
        *,
        generate_summary: bool = False,
        diff_chunks: bool = False,
        encoding: str = "utf-8",
    ) -> TranscriptEnhancerResult:
        transcript_path = Path(file_path)
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")
        if transcript_path.suffix.lower() != ".txt":
            raise ValueError("TranscriptEnhancer currently supports .txt files only")

        transcript_text = transcript_path.read_text(encoding=encoding)
        result = self.enhance_text(
            transcript_text,
            generate_summary=generate_summary,
            diff_chunks=diff_chunks,
        )
        result.source_file = transcript_path.name
        return result

    @staticmethod
    def _default_model_for_config(config: dict) -> str:
        return DEFAULT_MODEL_AZURE if config.get("use_azure", False) else DEFAULT_MODEL_OPENAI

    def _enhance_pass1(self, transcript_text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PASS1_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Edit this Finnish transcript for spelling consistency:\n\n{transcript_text}",
                },
            ],
            temperature=0.0,
        )
        return self._extract_response_text(response, transcript_text)

    def _enhance_pass2(self, transcript_text: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": PASS2_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Repair remaining ASR errors in this Finnish transcript:\n\n{transcript_text}",
                },
            ],
            temperature=0.0,
        )
        return self._extract_response_text(response, transcript_text)

    @staticmethod
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

    @staticmethod
    def _summarize_corrections(original_text: str, enhanced_text: str) -> CorrectionSummary:
        original_tokens = original_text.split()
        enhanced_tokens = enhanced_text.split()
        matcher = SequenceMatcher(a=original_tokens, b=enhanced_tokens)

        insertions = 0
        deletions = 0
        substitutions = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert":
                insertions += j2 - j1
            elif tag == "delete":
                deletions += i2 - i1
            elif tag == "replace":
                original_len = i2 - i1
                enhanced_len = j2 - j1
                substitutions += min(original_len, enhanced_len)
                if enhanced_len > original_len:
                    insertions += enhanced_len - original_len
                elif original_len > enhanced_len:
                    deletions += original_len - enhanced_len

        return CorrectionSummary(
            total_changes=insertions + deletions + substitutions,
            insertions=insertions,
            deletions=deletions,
            substitutions=substitutions,
        )

    @staticmethod
    def _build_diff_chunks(original_text: str, enhanced_text: str) -> list[DiffChunk]:
        original_tokens = original_text.split()
        enhanced_tokens = enhanced_text.split()
        matcher = SequenceMatcher(a=original_tokens, b=enhanced_tokens)

        return [
            DiffChunk(
                kind="substitute" if tag == "replace" else tag,
                original=" ".join(original_tokens[i1:i2]),
                corrected=" ".join(enhanced_tokens[j1:j2]),
            )
            for tag, i1, i2, j1, j2 in matcher.get_opcodes()
            if tag != "equal"
        ]
