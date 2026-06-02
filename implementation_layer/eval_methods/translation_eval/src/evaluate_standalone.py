"""
Standalone translation evaluation.

Evaluates all translation files in data/translation_results/ against the matching
reference files in data/ground_truth/ using four complementary metrics:
BLEU, chrF, TER, and Cosine Similarity. Reports only the aggregate averages.

The provided sample data uses 10 files from a Finnish-to-English dental domain
evaluation (gpt-5.1 model outputs). Replace the files in data/ground_truth/ and
data/translation_results/ with your own data to evaluate your own pipeline.

Usage:
    python evaluate_standalone.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import spacy
from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from nltk.translate.chrf_score import sentence_chrf
from torchmetrics.text import TranslationEditRate
from sentence_transformers import SentenceTransformer

# Inline clean_text_translation — avoids importing TermsGenerate (which pulls in stanza).
# Uses spacy lemmatization: keeps only alphabetic tokens in their base form.
_nlp = spacy.load("en_core_web_sm")


def clean_text_translation(text: str) -> str:
    return " ".join([t.lemma_ for t in _nlp(text) if t.is_alpha])


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BASE           = Path(__file__).parent.parent
GT_DIR          = _BASE / "data/ground_truth"
TRANSLATION_DIR = _BASE / "data/translation_results/gpt-5.1"
MODEL_NAME      = "gpt-5.1"

# ---------------------------------------------------------------------------
# Load models (once)
# ---------------------------------------------------------------------------

print("Loading models...")
transformer_model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
ter_metric        = TranslationEditRate()
smoothing         = SmoothingFunction().method1
print("Models loaded.\n")

# ---------------------------------------------------------------------------
# Evaluate all file pairs
# ---------------------------------------------------------------------------

gt_files = sorted(GT_DIR.glob("*.txt"))
assert gt_files, f"No .txt files found in {GT_DIR}"

bleu_scores, chrf_scores, ter_scores, cosine_scores = [], [], [], []
evaluated = 0

print(f"{'File':<50} {'BLEU':>7} {'chrF':>7} {'TER':>7} {'Cosine':>8}")
print("-" * 82)

for gt_file in gt_files:
    trans_file = TRANSLATION_DIR / gt_file.name
    if not trans_file.exists():
        print(f"  [SKIP] No matching translation for {gt_file.name}")
        continue

    gt_raw  = gt_file.read_text(encoding="utf-8")
    hyp_raw = trans_file.read_text(encoding="utf-8")

    gt_clean  = clean_text_translation(gt_raw)
    hyp_clean = clean_text_translation(hyp_raw)
    gt_tokens  = gt_clean.split()
    hyp_tokens = hyp_clean.split()

    bleu   = sentence_bleu([gt_tokens], hyp_tokens, smoothing_function=smoothing) * 100
    chrf   = sentence_chrf(gt_clean, hyp_clean) * 100
    ter    = ter_metric([hyp_clean], [[gt_clean]]).item() * 100
    emb_gt  = transformer_model.encode(gt_raw,  convert_to_numpy=True)
    emb_hyp = transformer_model.encode(hyp_raw, convert_to_numpy=True)
    cosine  = float(np.dot(emb_gt, emb_hyp) / (np.linalg.norm(emb_gt) * np.linalg.norm(emb_hyp))) * 100

    bleu_scores.append(bleu)
    chrf_scores.append(chrf)
    ter_scores.append(ter)
    cosine_scores.append(cosine)
    evaluated += 1

    print(f"  {gt_file.name:<48} {bleu:7.2f} {chrf:7.2f} {ter:7.2f} {cosine:8.2f}")

# ---------------------------------------------------------------------------
# Report averages only
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print(f"TRANSLATION EVALUATION — {MODEL_NAME}")
print(f"Files evaluated: {evaluated}")
print("=" * 60)
print(f"  BLEU            : {sum(bleu_scores)/evaluated:.2f}%   (higher is better; n-gram overlap)")
print(f"  chrF            : {sum(chrf_scores)/evaluated:.2f}%   (higher is better; character n-gram F-score)")
print(f"  TER             : {sum(ter_scores)/evaluated:.2f}%   (lower is better; edit rate)")
print(f"  Cosine Sim      : {sum(cosine_scores)/evaluated:.2f}%   (higher is better; semantic similarity)")
print("=" * 60)
