import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# these should match exactly or more than 95%
EXACT_FIELDS = [
    "Raportin tyyppi","Tarkkailijan nimi","Tarkkailijaorganisaatio",
    "Tarkkailija on kesätyöntekijä","Tapahtuma-aika",
    "Sijaintitiedot","Kuva","Tapahtuma oli vakava"
]

# these should match but not less than 80%
SEMANTIC_FIELDS = [
    "Tapahtuma-alueen kuvaus","Mahdolliset seuraukset",
    "Toteutetut toimenpiteet","Ehdotus"
]

ALL_FIELDS = EXACT_FIELDS + SEMANTIC_FIELDS

EXACT_THRESHOLD = 0.95
SEMANTIC_THRESHOLD = 0.80

# we use ground truth here
def evaluate_field_matching(ground_truth_dir: Path, prediction_dir: Path, output_file: Path, model_name: str = "all-MiniLM-L6-v2"):

    model = SentenceTransformer(model_name)

    tp_list, fp_list, fn_list, tn_list = [], [], [], []
    file_overall_scores = []
    exact_match_scores = []
    semantic_match_scores = []

    field_similarity_scores = defaultdict(list)

    with output_file.open("a", encoding="utf-8") as report:

        for gt_path in ground_truth_dir.iterdir():
            if gt_path.suffix != ".json":
                continue

            pred_path = prediction_dir / gt_path.name
            if not pred_path.exists():
                continue

            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            pred = json.loads(pred_path.read_text(encoding="utf-8"))

            gt_fields = set(gt.keys())
            pred_fields = set(pred.keys())
            field_set = set(ALL_FIELDS)

            # extracted fields evaluation not field values
            tp = len(field_set & gt_fields & pred_fields)
            fn = len((field_set & gt_fields) - pred_fields)
            fp = len((pred_fields - gt_fields) & field_set)
            tn = len(field_set - (gt_fields | pred_fields))

            tp_list.append(tp)
            fp_list.append(fp)
            fn_list.append(fn)
            tn_list.append(tn)

            report.write(f"\nFILE: {gt_path.name}\n")
            report.write("-" * 50 + "\n")

            matched_fields = 0
            evaluated_fields = 0

            exact_matched = 0
            exact_evaluated = 0
            semantic_matched = 0
            semantic_evaluated = 0

            for field in field_set & gt_fields & pred_fields:
                gt_val = str(gt[field]).strip()
                pred_val = str(pred[field]).strip()

                if not gt_val or not pred_val:
                    continue

                emb_gt = model.encode(gt_val)
                emb_pred = model.encode(pred_val)
                sim = cosine_similarity([emb_gt], [emb_pred])[0][0]

                field_similarity_scores[field].append(sim)

                threshold = EXACT_THRESHOLD if field in EXACT_FIELDS else SEMANTIC_THRESHOLD
                status = "PASS" if sim >= threshold else "ERROR"

                if status == "PASS":
                    matched_fields += 1
                    if field in EXACT_FIELDS:
                        exact_matched += 1
                    else:
                        semantic_matched += 1

                evaluated_fields += 1
                if field in EXACT_FIELDS:
                    exact_evaluated += 1
                else:
                    semantic_evaluated += 1

                report.write(
                    f"{field} | similarity={sim:.3f} | threshold={threshold} | {status}\n"
                )

            overall_match = (matched_fields / evaluated_fields) if evaluated_fields else 0
            exact_match = (exact_matched / exact_evaluated) if exact_evaluated else 0
            semantic_match = (semantic_matched / semantic_evaluated) if semantic_evaluated else 0

            file_overall_scores.append(overall_match)
            exact_match_scores.append(exact_match)
            semantic_match_scores.append(semantic_match)

            report.write(f"\nFile Overall Matching: {overall_match:.2%}\n")
            report.write(f"Exact Fields Matching: {exact_match:.2%}\n")
            report.write(f"Semantic Fields Matching: {semantic_match:.2%}\n")

        # overall averages for all files
        report.write("\n" + "=" * 60 + "\n")
        report.write("_*_* MODEL AVERAGES\n\n") #change model name

        report.write(f"Avg TP: {np.mean(tp_list):.2f}\n")
        report.write(f"Avg FP: {np.mean(fp_list):.2f}\n")
        report.write(f"Avg FN: {np.mean(fn_list):.2f}\n")
        report.write(f"Avg TN: {np.mean(tn_list):.2f}\n")

        report.write(f"\nAvg Overall Matching: {np.mean(file_overall_scores):.2%}\n")
        report.write(f"Avg Exact Fields Matching: {np.mean(exact_match_scores):.2%}\n")
        report.write(f"Avg Semantic Fields Matching: {np.mean(semantic_match_scores):.2%}\n")

        report.write("\n" + "=" * 60 + "\n")
        report.write("FIELD-WISE AVERAGE SIMILARITY\n")
        report.write("-" * 50 + "\n")

        for field in ALL_FIELDS:
            if field_similarity_scores[field]:
                report.write(
                    f"{field}: {np.mean(field_similarity_scores[field]):.4f}\n"
                )
            else:
                report.write(f"{field}: N/A\n")
