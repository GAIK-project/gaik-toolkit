import json
import re
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI
from collections import defaultdict
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# The fields requiring exact match
EXACT_FIELDS = [
    "raportinTyyppi",
    "tarkkailijanNimi",
    "tarkkailijanOrganisaatio",
    "tarkkailijaOnKesatyontekija",
    "paivamaara",
    "kellonaika",
    "lahellaPitiTilanne",
]

# The fields requiring semantic matching
SEMANTIC_FIELDS = [
    "rakennus",
    "tapahtumapaikanTarkenne",
    "mitaTapahtui",
    "mahdollisetSeuraukset",
    "toteutetutToimenpiteet",
    "ehdotus",
]

# The order in which the fields should appear
FIELD_ORDER = [
    "raportinTyyppi",
    "tarkkailijanNimi",
    "tarkkailijanOrganisaatio",
    "tarkkailijaOnKesatyontekija",
    "paivamaara",
    "kellonaika",
    "rakennus",
    "tapahtumapaikanTarkenne",
    "mitaTapahtui",
    "lahellaPitiTilanne",
    "mahdollisetSeuraukset",
    "toteutetutToimenpiteet",
    "ehdotus",
]

ALL_FIELDS = FIELD_ORDER
SIM_THRESHOLD = 0.50
MODEL_NAME = "text-embedding-3-large"
GT_FOLDER = Path("data/ground truth/")
SAMPLE_FOLDER = Path("data/predictions/")
REPORT_FILE = Path("IE_report_70%.txt")


def normalize(text):
    if text is None:
        return ""
    text = str(text).lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def normalize_date(text):
    text = str(text).strip()

    # ISO: yyyy-mm-dd
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return f"{int(m.group(3))}.{int(m.group(2))}.{m.group(1)}"

    # Finnish full year: d.m.yyyy
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        return f"{int(m.group(1))}.{int(m.group(2))}.{m.group(3)}"

    # Finnish short year: d.m.yy
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2})", text)
    if m:
        year = "20" + m.group(3)
        return f"{int(m.group(1))}.{int(m.group(2))}.{year}"

    # Incomplete Finnish: d.m. (no year)
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.", text)
    if m:
        return f"{int(m.group(1))}.{int(m.group(2))}."

    return normalize(text)


def get_embedding(text):
    response = client.embeddings.create(model=MODEL_NAME, input=text)
    return response.data[0].embedding


def cosine_sim(a, b):
    return cosine_similarity([a], [b])[0][0]


def compare_field(field, gt_value, sample_value):
    gt_value = "" if gt_value is None else str(gt_value).strip()
    sample_value = "" if sample_value is None else str(sample_value).strip()

    if gt_value == "" and sample_value == "":
        return "TN"

    if gt_value == "" and sample_value != "":
        return "FP"

    if gt_value != "" and sample_value == "":
        return "FN"

    if field in EXACT_FIELDS:
        if field == "paivamaara":
            match = normalize_date(gt_value) == normalize_date(sample_value)
        else:
            match = normalize(gt_value) == normalize(sample_value)

        if match:
            return "TP"
        else:
            return "BOTH_ERR"

    elif field in SEMANTIC_FIELDS:
        emb1 = get_embedding(gt_value)
        emb2 = get_embedding(sample_value)

        sim = cosine_sim(emb1, emb2)

        if sim >= SIM_THRESHOLD:
            return "TP"
        else:
            return "BOTH_ERR"

    return None


def compute_metrics(tp, tn, fp, fn):
    if tn > 0 and tp == 0 and fp == 0 and fn == 0:
        return None, None, None

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    return precision, recall, f1


def evaluate():
    file_results = []
    field_results = defaultdict(lambda: {"TP": 0, "TN": 0, "FP": 0, "FN": 0})

    total_TP = total_TN = total_FP = total_FN = 0
    total_files = 0

    for gt_file in sorted(GT_FOLDER.iterdir()):
        if gt_file.suffix != ".json":
            continue

        sample_file = SAMPLE_FOLDER / gt_file.name
        if not sample_file.exists():
            continue

        total_files += 1

        with open(gt_file) as f:
            gt = json.load(f)

        with open(sample_file) as f:
            sample = json.load(f)

        TP = TN = FP = FN = 0

        for field in ALL_FIELDS:
            gt_value = gt.get(field)
            sample_value = sample.get(field)

            result = compare_field(field, gt_value, sample_value)

            if result == "TP":
                TP += 1
                field_results[field]["TP"] += 1

            elif result == "TN":
                TN += 1
                field_results[field]["TN"] += 1

            elif result == "FP":
                FP += 1
                field_results[field]["FP"] += 1

            elif result == "FN":
                FN += 1
                field_results[field]["FN"] += 1

            elif result == "BOTH_ERR":
                FP += 1
                FN += 1
                field_results[field]["FP"] += 1
                field_results[field]["FN"] += 1

        precision, recall, f1 = compute_metrics(TP, TN, FP, FN)

        file_results.append(
            {
                "file": gt_file.name,
                "TP": TP,
                "TN": TN,
                "FP": FP,
                "FN": FN,
                "precision": round(precision, 4) if precision is not None else None,
                "recall": round(recall, 4) if recall is not None else None,
                "f1": round(f1, 4) if f1 is not None else None,
            }
        )

        total_TP += TP
        total_TN += TN
        total_FP += FP
        total_FN += FN

    avg_TP = total_TP / total_files
    avg_TN = total_TN / total_files
    avg_FP = total_FP / total_files
    avg_FN = total_FN / total_files

    precision, recall, f1 = compute_metrics(total_TP, total_TN, total_FP, total_FN)

    return (
        file_results,
        field_results,
        total_TP,
        total_TN,
        total_FP,
        total_FN,
        avg_TP,
        avg_TN,
        avg_FP,
        avg_FN,
        precision,
        recall,
        f1,
        total_files,
    )


def fmt(val, decimals=4):
    if val is None:
        return "N/A"
    return f"{round(val, decimals)}"


def write_report():
    (
        file_results,
        field_results,
        total_TP,
        total_TN,
        total_FP,
        total_FN,
        avg_TP,
        avg_TN,
        avg_FP,
        avg_FN,
        precision,
        recall,
        f1,
        total_files,
    ) = evaluate()

    def is_na(d):
        return d["TN"] > 0 and d["TP"] == 0 and d["FP"] == 0 and d["FN"] == 0

    exact_active = [f for f in EXACT_FIELDS if not is_na(field_results[f])]
    exact_tp_total = sum(field_results[f]["TP"] for f in exact_active)
    exact_tn_total = sum(field_results[f]["TN"] for f in exact_active)
    total_exact_evaluated = len(exact_active) * total_files
    exact_match_rate = (
        (exact_tp_total + exact_tn_total) / total_exact_evaluated if total_exact_evaluated else 0
    )

    sem_active = [f for f in SEMANTIC_FIELDS if not is_na(field_results[f])]
    semantic_tp_total = sum(field_results[f]["TP"] for f in sem_active)
    semantic_tn_total = sum(field_results[f]["TN"] for f in sem_active)
    total_semantic_evaluated = len(sem_active) * total_files
    semantic_match_rate = (
        (semantic_tp_total + semantic_tn_total) / total_semantic_evaluated
        if total_semantic_evaluated
        else 0
    )

    field_metrics = {}
    prec_vals = []
    rec_vals = []
    f1_vals = []

    for field in FIELD_ORDER:
        data = field_results[field]
        p, r, f1_field = compute_metrics(data["TP"], data["TN"], data["FP"], data["FN"])
        field_metrics[field] = (p, r, f1_field)
        if p is not None:
            prec_vals.append(p)
            rec_vals.append(r)
            f1_vals.append(f1_field)

    avg_prec = sum(prec_vals) / len(prec_vals) if prec_vals else 0
    avg_rec = sum(rec_vals) / len(rec_vals) if rec_vals else 0
    avg_f1 = sum(f1_vals) / len(f1_vals) if f1_vals else 0

    col_w = 30
    num_w = 6
    met_w = 8
    header = (
        f"{'Field':<{col_w}}"
        f"{'TP':>{num_w}}{'TN':>{num_w}}{'FP':>{num_w}}{'FN':>{num_w}}"
        f"{'Prec.':>{met_w}}{'Rec.':>{met_w}}{'F1':>{met_w}}"
    )
    sep = "-" * len(header)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("========== FIELD-LEVEL RESULTS ==========\n\n")
        f.write(header + "\n")
        f.write(sep + "\n")

        for field in FIELD_ORDER:
            data = field_results[field]
            p, r, f1_field = field_metrics[field]
            f.write(
                f"{field:<{col_w}}"
                f"{data['TP']:>{num_w}}{data['TN']:>{num_w}}{data['FP']:>{num_w}}{data['FN']:>{num_w}}"
                f"{fmt(p):>{met_w}}{fmt(r):>{met_w}}{fmt(f1_field):>{met_w}}\n"
            )

        f.write(sep + "\n")
        f.write(
            f"{'Overall Average':<{col_w}}"
            f"{'':>{num_w}}{'':>{num_w}}{'':>{num_w}}{'':>{num_w}}"
            f"{fmt(avg_prec):>{met_w}}{fmt(avg_rec):>{met_w}}{fmt(avg_f1):>{met_w}}\n"
        )

        f.write(
            f"\n(N/A fields excluded from overall average. {len(prec_vals)}/{len(FIELD_ORDER)} fields included.)\n"
        )

        f.write("\n\n========== FILE-LEVEL RESULTS ==========\n\n")

        file_header = (
            f"{'File':<{col_w}}"
            f"{'TP':>{num_w}}{'TN':>{num_w}}{'FP':>{num_w}}{'FN':>{num_w}}"
            f"{'Prec.':>{met_w}}{'Rec.':>{met_w}}{'F1':>{met_w}}"
        )
        f.write(file_header + "\n")
        f.write(sep + "\n")

        for r in sorted(file_results, key=lambda x: x["file"]):
            f.write(
                f"{r['file']:<{col_w}}"
                f"{r['TP']:>{num_w}}{r['TN']:>{num_w}}{r['FP']:>{num_w}}{r['FN']:>{num_w}}"
                f"{fmt(r['precision']):>{met_w}}{fmt(r['recall']):>{met_w}}{fmt(r['f1']):>{met_w}}\n"
            )

        f.write("\n\n========== AGGREGATE RESULTS ==========\n\n")

        f.write(f"Total files evaluated:  {total_files}\n")
        f.write(f"Total fields per file:  {len(FIELD_ORDER)}\n\n")

        f.write(
            f"Total TP: {total_TP}    Total TN: {total_TN}    Total FP: {total_FP}    Total FN: {total_FN}\n\n"
        )

        f.write(
            f"Precision  (P)  = TP/(TP+FP):              {fmt(precision)}  ({round(precision * 100, 2) if precision is not None else 'N/A'}%)\n"
        )
        f.write(
            f"Recall     (R)  = TP/(TP+FN):              {fmt(recall)}  ({round(recall * 100, 2) if recall is not None else 'N/A'}%)\n"
        )
        f.write(
            f"F1 Score   (F1) = 2·P·R/(P+R):             {fmt(f1)}  ({round(f1 * 100, 2) if f1 is not None else 'N/A'}%)\n"
        )
        f.write(
            f"Exact Match Rate  (EMR) = (TP+TN)/(All):   {fmt(exact_match_rate)}  ({round(exact_match_rate * 100, 2)}%)\n"
        )
        f.write(
            f"Semantic Match Rate (SMR) = (TP+TN)/(All): {fmt(semantic_match_rate)}  ({round(semantic_match_rate * 100, 2)}%)\n"
        )


write_report()

print("Evaluation completed.")
print("Report saved to:", REPORT_FILE)
