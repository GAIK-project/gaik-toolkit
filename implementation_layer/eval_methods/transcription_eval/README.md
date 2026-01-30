# Transcription Evaluation

Evaluation methods for assessing audio/video transcription quality and post-transcript enhancement effectiveness.

## Purpose

This evaluation suite provides:

- **Quantitative Metrics**: WER, CER, Spelling Error Rate for transcription accuracy
- **Side-by-Side Comparison**: Visual alignment of hypothesis vs. reference transcripts
- **Post-Transcript Enhancement**: GPT-5.1 based two-pass enhancement with domain-specific dictionaries
- **Benchmark Comparisons**: Evaluate multiple transcription models against ground truth for Finnish dental videos
- **Error Classification**: Systematic categorization of transcription errors for domain-specific videos

## Contents

### **Evaluation Scripts**

- **`side_by_side_compare.py`** - Compares hypothesis transcripts against reference transcripts, generates per-file reports with metrics and aligned output
- **`eval_enhanced.py`** - Compares original vs. enhanced transcripts against ground truth, reports aggregate improvement metrics
- **`enhance_transcript.py`** - Two-pass GPT-5.1 enhancement with dental-domain Finnish dictionary

### **Configuration & Utilities**

- **`config.py`** - Shared OpenAI/Azure OpenAI configuration
- **`requirements.txt`** - Python dependencies (jiwer, rapidfuzz, openai, python-dotenv)

### **Sample Data & Documentation**

- **`data/Ajokortti.mp3`** - Sample Finnish dental webinar audio
- **`data/reference.txt`** - Ground truth transcript for sample audio
- **`data/side-by-side-comparison.txt`** - Example evaluation report with aligned comparison
---

## Understanding Word Error Rate (WER)

### Definition

**Word Error Rate (WER)** is the standard metric for measuring speech-to-text accuracy. It quantifies the percentage of words that were incorrectly transcribed compared to a reference transcript.

### Formula

```
WER = (S + D + I) / N × 100%
```

Where:
- **S (Substitutions)**: Words replaced with incorrect words
- **D (Deletions)**: Words omitted from the transcript
- **I (Insertions)**: Extra words added that weren't spoken
- **N**: Total number of words in the reference transcript

### WER Interpretation Guidelines

| WER Range | Assessment | Typical Applications |
|-----------|-----------|---------------------|
| **< 5%** | Excellent | High-quality dictation, closed captions, medical transcription |
| **5-10%** | Very Good | Voice assistants in clean conditions, professional transcription |
| **10-20%** | Good | Meeting transcription, general-purpose STT |
| **20-30%** | Fair | Noisy environments, casual conversations |
| **> 30%** | Poor | Very challenging audio (heavy accents, background noise) |

*Source: [What is WER in Speech-to-Text - Vatis Tech 2025](https://vatis.tech/blog/what-is-wer-in-speech-to-text-everything-you-need-to-know-2025)*

---

## Finnish Dental Video Transcription Benchmarks

### Evaluation Context

**Domain**: Finnish dental webinars (implantology, prosthetics, periodontology)

**Language**: Finnish (morphologically complex, case inflections, compounds)

**Content**: Technical terminology, brand names, proper nouns, mixed Finnish-English loanwords

**Audio Quality**: Varies (professional recording to field conditions)

### Models Evaluated and Benchmarks

Comprehensive evaluation of multiple transcription models on Finnish dental webinar audio. Results show performance before and after GPT-5.1 post-transcript enhancement.

| Model | Original WER | Enhanced WER | Original Spelling | Enhanced Spelling | Original Substitution | Enhanced Substitution | Original Deletion | Enhanced Deletion | Original Insertion | Enhanced Insertion |
|-------|-------------|-------------|------------------|------------------|---------------------|---------------------|------------------|------------------|-------------------|-------------------|
| **Whisper (OpenAI/QADental)** | 22.98% | 21.00% | 4.92% | 3.68% | 10.65% | 8.98% | 10.24% | 10.14% | 2.08% | 1.88% |
| **gpt-4o-transcribe** | 18.30% | **17.04%** | 4.76% | 4.07% | 9.08% | 7.87% | 7.18% | 7.10% | 2.03% | 2.06% |
| **WhisperX (large-v3)** | 17.83% | **16.06%** | 4.50% | 3.76% | 9.37% | 8.11% | 6.28% | 6.07% | 2.19% | 1.88% |
| **WhisperX (large-v2)** | 26.66% | 24.58% | 4.55% | 3.76% | 11.07% | 9.37% | 11.37% | 11.14% | 4.22% | 4.07% |
| **WhisperX (large)** | 17.83% | **15.98%** | 4.50% | 3.83% | 9.37% | 7.98% | 6.28% | 6.15% | 2.19% | 1.85% |
| **Gemini-2.5-pro** | 25.32% | 23.47% | 5.07% | 4.97% | 11.61% | 10.78% | 1.54% | 1.26% | 12.17% | 11.43% |
| **Gemini-3-flash-preview** | 27.53% | 26.69% | 6.48% | 6.33% | 15.88% | 15.47% | 2.44% | 2.19% | 9.21% | 9.03% |
| **WhisperX (medium)** | 28.10% | 24.02% | 6.09% | 4.45% | 12.99% | 9.54% | 11.06% | 10.60% | 4.05% | 3.88% |
| **WhisperX (small)** | 33.66% | 24.70% | 9.32% | 5.58% | 20.77% | 13.66% | 8.29% | 7.44% | 4.61% | 3.60% |
| **WhisperX (tiny)** | 70.12% | 53.58% | 11.14% | 7.77% | 46.94% | 35.07% | 10.24% | 9.19% | 12.94% | 9.32% |

**Key Findings:**
- **Best Original Performance**: WhisperX (large) and WhisperX (large-v3) achieve ~17.83% WER
- **Best Enhanced Performance**: WhisperX (large) at 15.98% WER after GPT-5.1 enhancement
- **Most Improved**: WhisperX (small) shows 8.96 percentage point improvement (33.66% → 24.70%)
- **Post-Enhancement Impact**: All models benefit from enhancement, with avg. 1.5-3% WER reduction
- **Spelling Error Reduction**: Enhancement consistently reduces spelling errors by 0.5-3.5%
- **Gemini Models**: Show higher insertion rates but lower deletion rates compared to Whisper variants

**Model Selection Guidance:**
- **Production Use**: WhisperX (large-v3) or gpt-4o-transcribe for best balance of accuracy and reliability
- **Resource-Constrained**: WhisperX (medium) with enhancement achieves 24% WER with smaller footprint
- **Cost-Optimized**: WhisperX (small) + enhancement provides acceptable quality at lower compute cost

### Error Type Classification by Fix Stage

Based on systematic analysis of Finnish dental video transcriptions, errors are classified by the stage at which they can be addressed:

#### **1. Model-Level Fixes (Transcription Stage)**

These errors must be addressed through model fine-tuning or training data improvements:

| Error Type | Description | Examples | Why Model-Level |
|-----------|-------------|----------|----------------|
| **Catastrophic Omissions** | Large consecutive deletions (entire phrases missing) | Long [D:...] runs spanning multiple words/phrases | Cannot be reliably reconstructed post-transcript; requires better acoustic modeling |

**Fix Strategy**: Fine-tuning on domain-specific data, better acoustic models, improved voice activity detection

---

#### **2. Post-Transcription Level Fixes**

These errors can be corrected through post-processing with LLMs, dictionaries, or rule-based systems:

| Error Type | Description | Examples | Fix Strategy |
|-----------|-------------|----------|--------------|
| **Brands/Proper Nouns Garbled** | Brand/company names become phonetically similar nonsense | Straumann → Strauman<br>Dentsply Sirona → Splacirona<br>Nobel Biocare → Nobel Pajaker<br>Implantona → Implanttoona | Dictionary + fuzzy matching |
| **Name Alterations** | Person names/surnames wrong (near-miss) | Martola/Martoon<br>Pallonen/Pallosen<br>Suojärvi/Suojärven | Dictionary-mapped variants |
| **Compound/Hyphenation** | Compounds split/merged inconsistently | peri-implantiitti ↔ periimplantiitti | Consistency normalization |
| **Loanword Distortion** | English technical terms misheard as Finnish | lowdose → loudausohjelmia | Bilingual domain lexicon |
| **Number Format** | Digits vs. Finnish number words | kahdenkymmenen → 20<br>viisikymmentäkuusi → 56 | Number normalizer |
| **Decimal Tokenization** | Spoken math becomes wrong tokens | "X ja puoli" → 375 (intended 37.5) | Finnish number normalizer |
| **Finnish Morphology** | Wrong case/number endings (same lemma) | Plural/singular drift, case variations | Finnish-aware inflection |

**Fix Strategy**: Two-pass GPT-5.1 enhancement (Pass 1: spelling/consistency, Pass 2: context repair)

---

#### **3. Evaluation-Level Normalization**

These aren't true errors but evaluation artifacts from formatting/tokenization differences:

| Error Type | Description | Examples | Fix Strategy |
|-----------|-------------|----------|--------------|
| **Evaluation Artifacts** | Style differences penalized by WER | hands-on ↔ handson<br>hyphen/spacing differences | Pre-evaluation normalization of reference and hypothesis |

**Fix Strategy**: Apply consistent formatting rules to both reference and hypothesis before WER calculation

---

#### **4. "Live With" Errors**

These errors have minimal impact on meaning and are often acceptable in production:

| Error Type | Description | Examples | Why Acceptable |
|-----------|-------------|----------|---------------|
| **Function Word Deletions** | Short glue words missing | Frequent [D:ja], [D:että], [D:se] | Meaning survives; Finnish allows some ellipsis in spoken language |
| **Filler Insertions** | Extra discourse words | ... [I] around sentence starts | Doesn't change core meaning; reflects natural speech patterns |

**Decision Criteria**: If transcript is still comprehensible and semantically correct, minor function word errors can be accepted to avoid over-correction risks.

---

## Installation & Setup

### 1. Install Dependencies

```bash
cd implementation_layer/eval_methods/transcription_eval
pip install -r requirements.txt
```

**Dependencies:**
- `jiwer==4.0.0` - Word error rate calculation
- `rapidfuzz==3.14.3` - Levenshtein distance for spelling errors
- `python-dotenv==1.2.1` - Environment variable management
- `openai==1.109.1` - OpenAI/Azure OpenAI API client

### 2. Configure API Access

Set environment variables for GPT-5.1 enhancement:

**Azure OpenAI:**
```bash
export AZURE_API_KEY="your-api-key"
export AZURE_ENDPOINT="https://your-endpoint.openai.azure.com/"
```

**Standard OpenAI:**
```bash
export OPENAI_API_KEY="sk-your-api-key"
```

Update `config.py` line 37 to set `use_azure=False` if using standard OpenAI.

---

## Usage Guide

### Workflow 1: Evaluate Raw Transcription Quality

Compare ASR output (hypothesis) against ground truth (reference):

```bash
python side_by_side_compare.py <reference_dir> <hypothesis_dir> <output_dir>
```

**Example:**
```bash
python side_by_side_compare.py \
  reference_transcripts/ \
  whisper_output/ \
  evaluation_reports/
```

**Outputs:**
- Per-file reports with WER, CER, spelling error rate
- Side-by-side aligned comparison showing:
  - `[S]` = Substitution
  - `[S,C]` = Spelling error (close match, Levenshtein distance ≤ 40%)
  - `[D]` = Deletion
  - `[I]` = Insertion
- Aggregate statistics across all files

**Sample Output (sample video: data/Ajokortti.mp3, model: gpt-4o-transcribe):**

```
==================================================
TRANSCRIPTION ACCURACY REPORT
==================================================
Word Error Rate (WER):      16.67%
Character Error Rate (CER): 7.88%
Spelling Error Rate:        4.98%
Substitution Rate:          9.70%
Deletion Rate:              6.72%
Insertion Rate:             0.25%
--------------------------------------------------
Total words in reference:   402
Correct words:              336
Substitutions:              39
Insertions:                 1
Deletions:                  27
==================================================
```

**SIDE-BY-SIDE COMPARISON** (marked hypothesis, truncated):

**REF:** suojärven timon luento potilasvahingot protetiikassa siinä tulee hyvin laajasti protetiikkaa yleensä vähän vaikeusasteen arviointia ja muuta sitten

**HYP:** **koulutusta[I]** suojärven timon luento potilasvahingot protetiikassa siinä tulee hyvin laajasti protetiikkaa yleensä vähän vaikeusasteen arviointia ja muuta sitten

**REF:** on parodontologi martta martolan luento perimplantiitista ja sitten implantticaseja semmoinen vodcast jossa peterin kanssa käydään läpi näitä yleisiä

**HYP:** on parodontologi martta **martoon[S,C:martolan]** luento **periimplantiitista[S,C:perimplantiitista]** ja sitten **implanttikeissejä[S,C:implantticaseja]** semmoinen vodcast jossa **peetterin[S,C:peterin]** kanssa käydään läpi näitä **[D:yleisiä]**

**REF:** ongelmia tai yleisimpiä ongelmia mitä implanttien kanssa voi tulla ja ne on hyvä tunnistaa ja tietää miten ne

**HYP:** **[D:ongelmia] [D:tai]** yleisimpiä ongelmia mitä implanttien kanssa voi tulla ja ne on hyvä tunnistaa ja tietää miten ne

### Workflow 2: Enhance Transcripts with GPT-5.1

Apply two-pass enhancement with domain-specific dictionary:

```bash
python enhance_transcript.py \
  --transcripts-dir <input_dir> \
  --output-dir <enhanced_dir> \
  --model gpt-5.1
```

**Example:**
```bash
python enhance_transcript.py \
  --transcripts-dir whisper_output/ \
  --output-dir enhanced_transcripts/
```

**What Happens:**

**Pass 1 (Spelling Consistency):**
- Normalizes spelling using dental-focused Finnish dictionary
- Fixes capitalization (brands: Straumann, Nobel Biocare; names: Timo Suojärvi)
- Ensures consistent hyphenation (peri-implantiitti)
- **No word additions/deletions** (preserves word count)

**Pass 2 (Context-Based Repair):**
- Fixes ASR-specific errors (compound splitting: "reaali maailmassa" → "reaalimaailmassa")
- Inserts essential function words (`että`, `ja`, `niin`) when grammar requires it
- Converts numeric digits to Finnish word numbers with **correct inflection**
  - Genitive: "20 prosentin" → "kahdenkymmenen prosentin"
  - Nominative: "20 prosenttia" → "kaksikymmentä prosenttia"
- **Preserves colloquial Finnish** (spoken language: "tän", "tää", "niinku", "mä", "sä")
- Limited insertion budget: max 4 words per 100 words

**Output:**
```
Processing: Ajokortti.txt
  Original: 402 words
  Pass 1: Spelling consistency...
    -> 402 words (delta: 0)
  Pass 2: Context repair + number conversion...
    -> 405 words (delta: +3)
  Total change: 402 -> 405 words (+3)
  Saved to: enhanced_transcripts/Ajokortti.txt
```

### Workflow 3: Evaluate Enhancement Impact

Compare original vs. enhanced transcripts against ground truth:

```bash
python eval_enhanced.py <reference_dir> <original_dir> <enhanced_dir>
```

**Example:**
```bash
python eval_enhanced.py \
  reference_transcripts/ \
  whisper_output/ \
  enhanced_transcripts/
```

**Sample Output:**
```
================================================================================
EVALUATING ORIGINAL VS ENHANCED TRANSCRIPTS
================================================================================

Ajokortti | Orig: 16.67% | Enh: 14.18% | Delta: -2.49% | IMPROVED

================================================================================
SUMMARY
================================================================================
Files evaluated:     1
  Improved:          1
  Degraded:          0
  Unchanged:         0

================================================================================
AGGREGATE METRICS
================================================================================
Metric                         | Original   | Enhanced   | Change
--------------------------------------------------------------------------------
Word Error Rate (WER)          | 16.67%     | 14.18%     | -2.49%
Character Error Rate (CER)     | 7.88%      | 6.72%      | -1.16%
Spelling Error Rate            | 4.98%      | 3.23%      | -1.75%
Substitution Rate              | 9.70%      | 8.21%      | -1.49%
Deletion Rate                  | 6.72%      | 5.72%      | -1.00%
Insertion Rate                 | 0.25%      | 0.25%      | +0.00%
================================================================================

>>> Overall WER improved by 2.49 percentage points!
```

---

## Integration with GAIK Toolkit

### Evaluating GAIK Transcriber Component

Use these evaluation scripts to assess GAIK `Transcriber` output quality:

```python
from gaik.software_components.transcriber import Transcriber, get_openai_config
from pathlib import Path

# 1. Transcribe audio with GAIK
config = get_openai_config(use_azure=True)
transcriber = Transcriber(api_config=config, output_dir="transcripts/")
result = transcriber.transcribe("data/Ajokortti.mp3")

# 2. Save transcript for evaluation
output_file = Path("whisper_output/Ajokortti.txt")
output_file.write_text(result.raw_transcript, encoding="utf-8")

# 3. Evaluate against ground truth (using bash commands)
# python side_by_side_compare.py reference/ whisper_output/ reports/
```

### Supported Use Cases

This evaluation suite supports all GAIK transcription workflows listed in the main [README.md](../../../README.md#typical-gaik-workflows-this-toolkit-enables):

- **Incident Reporting** - Voice/recording → structured extraction → report generation
- **Construction Diary Creation** - Voice/recording + images → structured extraction → report
- **Transcription and Translation** - Domain-specific video transcription + translation
- **Construction Site Report Generation** - Multiple documents + images + audios + notes → structured report

---

## Domain Customization

### Adapting for Other Domains

To use this evaluation suite for non-dental domains:

1. **Update Dictionary** (`enhance_transcript.py`, lines 17-77):
   - Replace `DENTAL_DICTIONARY` with your domain terminology
   - Include: brands, technical terms, proper nouns, common misspellings

2. **Adjust Enhancement Prompts** (`PASS1_SYSTEM_PROMPT`, `PASS2_SYSTEM_PROMPT`):
   - Modify domain context (lines 81-116, 119-172)
   - Keep the structural constraints (word count limits, no paraphrasing)

3. **Language Adaptation**:
   - For non-Finnish: remove Finnish-specific inflection rules (line 138-146)
   - Adjust number conversion rules for target language
   - Update colloquial preservation list (line 148-151)

---

## Metrics Reference

### Word Error Rate (WER)
```
WER = (Substitutions + Deletions + Insertions) / Total Reference Words × 100%
```
Primary metric for transcription accuracy. Lower is better.

### Character Error Rate (CER)
```
CER = (Char Substitutions + Char Deletions + Char Insertions) / Total Ref Characters × 100%
```
More granular than WER, useful for morphologically complex languages.

### Spelling Error Rate
```
Spelling Error Rate = Spelling Substitutions / Total Reference Words × 100%
```
Counts only "close" substitutions (Levenshtein distance ≤ 40% of word length). Identifies ASR spelling/pronunciation errors vs. semantic errors.

### Component Rates

- **Substitution Rate**: Percentage of words incorrectly replaced
- **Deletion Rate**: Percentage of words omitted
- **Insertion Rate**: Percentage of extra words added

---

## Best Practices

### For Evaluation

1. **Use Consistent References**: Ensure ground truth transcripts are accurate and consistently formatted
2. **Normalize Before Evaluation**: Apply consistent capitalization, punctuation, and number format policies
3. **Batch Processing**: Evaluate multiple files together for aggregate statistics
4. **Document Audio Conditions**: Note audio quality, speaker characteristics, background noise

### For Enhancement

1. **Start with Pass 1 Only**: Test spelling/consistency fixes before context-based repair
2. **Monitor Word Count Delta**: Pass 2 should add ≤4 words per 100 words
3. **Validate Changes**: Manually review enhanced transcripts for meaning preservation
4. **Domain Dictionary**: Keep dictionary updated with new technical terms and brands
5. **Preserve Spoken Style**: Don't "correct" colloquial language to formal written language

### For Production Use

1. **Set WER Targets**: Define acceptable WER based on use case (< 10% for professional, < 20% for general)
2. **Track Degradation**: Monitor if enhancement ever degrades quality (should be rare)
3. **A/B Testing**: Compare enhanced vs. non-enhanced for your specific audio domain
4. **Cost-Benefit Analysis**: Enhancement adds API cost; ensure WER improvement justifies expense

---

## Troubleshooting

### High WER (> 30%)

**Possible Causes:**
- Poor audio quality (background noise, low volume, crosstalk)
- Heavy accents or non-native speakers
- Technical jargon not in model vocabulary
- Incorrect reference transcript

**Solutions:**
- Improve audio quality (noise reduction, better microphone)
- Fine-tune transcription model on domain-specific data
- Add domain terms to enhancement dictionary
- Verify reference transcript accuracy

### Enhancement Degrades Quality

**Possible Causes:**
- Dictionary contains incorrect mappings
- Pass 2 insertions change meaning
- Overly aggressive number conversion

**Solutions:**
- Review dictionary entries
- Reduce Pass 2 insertion budget
- Disable number conversion if not needed
- Test with Pass 1 only

### Encoding Errors

**Issue:** UnicodeEncodeError or garbled characters

**Solution:**
```python
# Ensure UTF-8 encoding for all file operations
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()
```

---

## Citation

If using this evaluation suite in research or publications, please reference:

**GAIK Transcription Evaluation Methods** (2025). Part of the GAIK Toolkit - Generative AI Knowledge Management.
GitHub: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
Project: [gaik.ai](https://gaik.ai)

---

## Related Resources

- **GAIK Transcriber Component**: [guidance_layer/docs/software_components/transcriber.md](../../../guidance_layer/docs/software_components/transcriber.md)
- **Main README**: [README.md](../../../README.md) - See "Typical GAIK workflows this toolkit enables"
- **Evaluation Methods Overview**: [../README.md](../README.md)
- **Project Website**: [gaik.ai](https://gaik.ai)
- **Documentation**: [https://gaik-project.github.io/gaik-toolkit/](https://gaik-project.github.io/gaik-toolkit/)

---

*Last Updated: January 2026*
*Part of the Implementation Layer in GAIK's layer-based architecture*
