# Transcript Evaluations

This repository contains three scripts used to enhance transcripts and evaluate
ASR output against reference transcripts.

## Files

- `side_by_side_compare.py`
  Compares hypothesis transcripts against reference transcripts and writes
  per-file reports with metrics and side-by-side alignment.

- `enhance_transcript.py`
  Enhances transcripts with GPT-5.1 (spelling/consistency fixes) and writes
  results to an output folder. Requires OpenAI/Azure OpenAI credentials.

- `eval_enhanced.py`
  Compares original vs enhanced transcripts against the same reference set and
  prints aggregate metrics for both.

## Requirements

Install Python dependencies from this folder:

```powershell
pip install -r requirements.txt
```

Set environment variables for API access if you plan to run enhancement:

- `AZURE_API_KEY` (if using Azure OpenAI) - use_azure = True
- `OPENAI_API_KEY` (if using OpenAI) - use_azure = False

## How To Run

Side-by-side evaluation (reference first, hypothesis second):

```powershell
python side_by_side_compare.py <reference_dir> <hypothesis_dir> <output_dir>
```

Compares reference and hypothesis transcripts and saves the side by side comparisons in output_dir.

Enhance transcripts:

```powershell
python enhance_transcript.py --transcripts-dir <input_dir> --output-dir <enhanced_dir>
```

input_dir is the directory containing raw transcripts.


Compare original vs enhanced against the same references:

```powershell
python eval_enhanced.py <reference_dir> <original_dir> <enhanced_dir>
```

## Evaluation Metrics

Definitions used in the evaluation reports:

- **WER (Word Error Rate)** = (Substitutions + Deletions + Insertions) / Total reference words
- **CER (Character Error Rate)** = (Character substitutions + deletions + insertions) / Total reference characters
- **Spelling Error Rate** = Spelling substitutions / Total reference words
- **Substitution Rate** = Substitutions / Total reference words
- **Deletion Rate** = Deletions / Total reference words
- **Insertion Rate** = Insertions / Total reference words

## Transcript Enhancement Approach

`enhance_transcript.py` runs two GPT-based passes over each transcript:

1) **Pass 1 (Spelling consistency):**
   Normalizes spelling, capitalization, and dental terminology using a
   domain-specific dictionary. The goal is to fix obvious errors without
   changing meaning or word order.

2) **Pass 2 (Context-based repair):**
   Uses surrounding context to fix remaining ASR errors such as split/merged
   compounds and optional filler words, while preserving the spoken style.
   Numeric digits may be converted to Finnish word forms with correct inflection.
