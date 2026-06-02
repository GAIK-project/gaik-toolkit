"""
translation_evaluation.py
BLEU / chrF / TER / Cosine Similarity evaluation for translation quality assessment.

Iterates over ALL model subdirectories in data/translation_results/ automatically.
Each subdirectory is treated as one model (e.g. data/translation_results/gpt-5.1/).
Matches messy hypothesis filenames to ground-truth files using fuzzy matching.

Outputs:
  evaluation_results/results.csv   — machine-readable, one row per file per model
  evaluation_results/results.txt   — human-readable per-model report

Usage:
  python scr/translation_evaluation.py
"""


import csv
from pathlib import Path
import numpy as np


from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu
from nltk.translate.chrf_score import sentence_chrf
from torchmetrics.text import TranslationEditRate
from sentence_transformers import SentenceTransformer
from rapidfuzz import process, fuzz

import spacy as _spacy
_nlp = _spacy.load("en_core_web_sm")

def clean_text_translation(text: str) -> str:
    return " ".join([t.lemma_ for t in _nlp(text) if t.is_alpha])

# 1. USER CONFIG
_BASE                = Path(__file__).parent.parent
REFERENCE_FOLDER     = _BASE / "data/ground_truth"
TOOL_RESULTS_FOLDER  = _BASE / "data/translation_results"  # subfolders = one model each
OUTPUT_FOLDER        = _BASE / "evaluation_results"

TARGET_MODELS        = []  



# 2. helper function to match fuzzy filenames

def _fuzzy_match_filename(target_name: str, candidate_paths: list) -> Path:
    """
    Given a ground truth filename (e.g. 'ABC_20210115_Final.txt'), 
    finds the best match in a list of Paths (e.g. 'ABCTranslated.txt').
    """
    candidate_names = [p.name for p in candidate_paths]
    # Use rapidfuzz to find the closest matching filename
    best_match_tuple = process.extractOne(target_name, candidate_names, scorer=fuzz.WRatio)
    
    if best_match_tuple and best_match_tuple[1] > 60: # Confidence threshold
        best_match_name = best_match_tuple[0]
        for p in candidate_paths:
            if p.name == best_match_name:
                return p
    return None


def evaluate_model(model_name: str, ref_dir: Path, hyp_dir: Path, txt_file, csv_writer, transformer_model, ter_metric):
    """Evaluates a single model against all ground truth files. Returns average scores dict or None."""

    ref_files = sorted(ref_dir.glob("*.txt"))
    if not ref_files:
        print(f"  ⚠️  No reference files found in {ref_dir}")
        return None

    hyp_files_available = list(hyp_dir.glob("*.txt"))
    n_ref = len(ref_files)

    total_bleu = total_ter = total_cos = total_chrf = 0
    evaluated = 0

    txt_file.write("\n" + "=" * 60 + "\n")
    txt_file.write(f"Model: {model_name}\n")
    txt_file.write("=" * 60 + "\n")

    for i, ref_file in enumerate(ref_files, 1):
        hyp_file = _fuzzy_match_filename(ref_file.name, hyp_files_available)

        if not hyp_file or not hyp_file.exists():
            print(f"  [{i}/{n_ref}] ⚠️  No match for {ref_file.name} — skipping.")
            continue

        print(f"  [{i}/{n_ref}] {ref_file.name}", end=" ... ", flush=True)

        with open(ref_file, "r", encoding="utf-8") as f:
            gt_text = f.read()
        with open(hyp_file, "r", encoding="utf-8") as f:
            hyp_text = f.read()

        gt_clean  = clean_text_translation(gt_text)
        hyp_clean = clean_text_translation(hyp_text)

        if not gt_clean:
            print("skipped (empty after cleaning)")
            continue

        gt_tokens  = gt_clean.split()
        hyp_tokens = hyp_clean.split()
        smoothie   = SmoothingFunction().method4
        bleu       = sentence_bleu([gt_tokens], hyp_tokens, smoothing_function=smoothie) * 100
        chrf       = sentence_chrf(gt_clean, hyp_clean) * 100
        ter        = ter_metric([hyp_clean], [[gt_clean]]).item() * 100
        emb_gt     = transformer_model.encode(gt_clean)
        emb_hyp    = transformer_model.encode(hyp_clean)
        cos_sim    = (np.dot(emb_gt, emb_hyp) / (np.linalg.norm(emb_gt) * np.linalg.norm(emb_hyp))) * 100

        print(f"BLEU={bleu:.1f}  chrF={chrf:.1f}  TER={ter:.1f}  Cosine={cos_sim:.1f}")

        txt_file.write(
            f"{ref_file.name} | BLEU={bleu:.2f} | chrF={chrf:.2f} | TER={ter:.2f} | Cosine={cos_sim:.2f}\n"
        )
        csv_writer.writerow({
            "model": model_name, "file": ref_file.name,
            "BLEU": round(bleu, 2), "chrF": round(chrf, 2),
            "TER": round(ter, 2), "CosineSim": round(cos_sim, 2),
            "type": "per_file"
        })

        total_bleu += bleu
        total_chrf += chrf
        total_ter  += ter
        total_cos  += cos_sim
        evaluated  += 1

    if evaluated == 0:
        txt_file.write("No files evaluated.\n")
        print(f"  ⚠️  {model_name}: no files evaluated.")
        return None

    avg_bleu = total_bleu / evaluated
    avg_chrf = total_chrf / evaluated
    avg_ter  = total_ter  / evaluated
    avg_cos  = total_cos  / evaluated

    txt_file.write(f"\n--- AVERAGE ({evaluated} files) ---\n")
    txt_file.write(f"BLEU={avg_bleu:.2f}\nchrF={avg_chrf:.2f}\nTER={avg_ter:.2f}\nCosineSim={avg_cos:.2f}\n")

    csv_writer.writerow({
        "model": model_name, "file": "AVERAGE",
        "BLEU": round(avg_bleu, 2), "chrF": round(avg_chrf, 2),
        "TER": round(avg_ter, 2), "CosineSim": round(avg_cos, 2),
        "type": "average"
    })

    print(f"  ─── Average: BLEU={avg_bleu:.2f}  chrF={avg_chrf:.2f}  TER={avg_ter:.2f}  Cosine={avg_cos:.2f}  ({evaluated}/{n_ref} files)")
    return {"model": model_name, "BLEU": avg_bleu, "chrF": avg_chrf, "TER": avg_ter, "CosineSim": avg_cos}



def main():
    ref_dir     = Path(REFERENCE_FOLDER)
    results_dir = Path(TOOL_RESULTS_FOLDER)
    out_dir     = Path(OUTPUT_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not ref_dir.exists():
        raise FileNotFoundError(f"Reference folder not found: {ref_dir}")
    if not results_dir.exists():
        raise FileNotFoundError(f"Translation results folder not found: {results_dir}")

    model_dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])

    if TARGET_MODELS:
        model_dirs = [d for d in model_dirs if d.name in TARGET_MODELS]
        suffix   = "_".join(TARGET_MODELS)
        txt_path = out_dir / f"results_{suffix}.txt"
        csv_path = out_dir / f"results_{suffix}.csv"
    else:
        txt_path = out_dir / "results.txt"
        csv_path = out_dir / "results.csv"

    if not model_dirs:
        raise FileNotFoundError(
            f"No model subdirectories found in {results_dir}. "
            f"Each model should be a subfolder, e.g. {results_dir}/gpt-5.1/"
        )

    print("=" * 70)
    print(f"Translation Evaluation")
    print(f"  Reference folder : {ref_dir}")
    print(f"  Models folder    : {results_dir}")
    print(f"  Models found     : {len(model_dirs)} — {[d.name for d in model_dirs]}")
    print(f"  Output           : {out_dir}")
    print("=" * 70)

    print("\nLoading SentenceTransformer and TER models (once for all models)...")
    transformer_model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    ter_metric        = TranslationEditRate()
    print("Models loaded.\n")

    csv_fields = ["model", "file", "BLEU", "chrF", "TER", "CosineSim", "type"]
    all_averages = []

    with (
        txt_path.open("w", encoding="utf-8") as txt_file,
        csv_path.open("w", newline="", encoding="utf-8") as csv_file,
    ):
        csv_writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
        csv_writer.writeheader()

        for idx, model_dir in enumerate(model_dirs, 1):
            print(f"\n[{idx}/{len(model_dirs)}] Evaluating: {model_dir.name}")
            print("-" * 70)
            result = evaluate_model(
                model_name=model_dir.name,
                ref_dir=ref_dir,
                hyp_dir=model_dir,
                txt_file=txt_file,
                csv_writer=csv_writer,
                transformer_model=transformer_model,
                ter_metric=ter_metric,
            )
            if result:
                all_averages.append(result)

    # Final summary table
    print("\n" + "=" * 70)
    print("SUMMARY — Average scores across all models")
    print("=" * 70)
    print(f"  {'Model':<20} {'BLEU':>7} {'chrF':>7} {'TER':>7} {'Cosine':>8}")
    print("  " + "-" * 50)
    for r in all_averages:
        print(f"  {r['model']:<20} {r['BLEU']:7.2f} {r['chrF']:7.2f} {r['TER']:7.2f} {r['CosineSim']:8.2f}")
    print("=" * 70)
    print(f"\n✅ Results written to:")
    print(f"   {txt_path}")
    print(f"   {csv_path}")

if __name__ == "__main__":
    main()