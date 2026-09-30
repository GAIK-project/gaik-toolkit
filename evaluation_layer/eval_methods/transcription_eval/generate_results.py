"""Redraw the historical WER chart and README table without API calls.

The CSV preserves previously published README values, not a fresh benchmark.
Run from any directory: python generate_results.py
"""

import csv
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START = "<!-- historical-results:start -->"
END = "<!-- historical-results:end -->"


def main():
    with (ROOT / "data/historical_results.csv").open(encoding="utf-8", newline="") as source:
        rows = sorted(csv.DictReader(source), key=lambda row: float(row["original_wer"]))
    width, left, scale, top, step = 960, 375, 6.6, 105, 52
    height = top + len(rows) * step + 30
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="title desc" font-family="Segoe UI, Arial, sans-serif">',
        '<title id="title">Historical transcription WER before and after enhancement</title>',
        '<desc id="desc">13 models, sorted by raw WER. Blue is raw, green is enhanced. '
        "Lower is better. Values preserved from the previous README; raw benchmark inputs "
        "and run settings are unavailable.</desc>",
        f'<rect width="{width}" height="{height}" rx="12" fill="#fcfcfb"/>',
        '<text x="24" y="32" font-size="20" fill="#17212b">'
        "Transcription WER: raw vs enhanced</text>",
        '<text x="24" y="55" font-size="13" fill="#536170">Historical reported results; '
        "not the QAD-1 rerun. Lower is better.</text>",
        '<rect x="24" y="73" width="12" height="12" fill="#2a78d6"/>',
        '<text x="43" y="84" font-size="13">Raw transcript</text>',
        '<rect x="174" y="73" width="12" height="12" fill="#168566"/>',
        '<text x="193" y="84" font-size="13">Enhanced transcript</text>',
    ]
    table = [
        "| Model | Raw WER % | Enhanced WER % | Reduction (percentage points) |",
        "|---|--:|--:|--:|",
    ]
    for index, row in enumerate(rows):
        label = row["model"]
        raw, enhanced = float(row["original_wer"]), float(row["enhanced_wer"])
        y = top + index * step
        svg.append(
            f'<text x="{left - 12}" y="{y + 23}" text-anchor="end" '
            f'font-size="12" fill="#17212b">{escape(label)}</text>'
        )
        for offset, value, color in [(0, raw, "#2a78d6"), (22, enhanced, "#168566")]:
            length = value * scale
            svg.append(
                f'<rect x="{left}" y="{y + offset}" width="{length:.2f}" height="17" '
                f'rx="3" fill="{color}"><title>{escape(label)}: {value:.2f}%</title></rect>'
            )
            svg.append(
                f'<text x="{left + length + 7:.2f}" y="{y + offset + 13}" '
                f'font-size="12" fill="#536170">{value:.2f}%</text>'
            )
        table.append(f"| {label} | {raw:.2f} | {enhanced:.2f} | {raw - enhanced:.2f} |")
    svg.append("</svg>")
    images = ROOT / "images"
    images.mkdir(exist_ok=True)
    (images / "historical-wer.svg").write_text(
        "\n".join(svg) + "\n", encoding="utf-8", newline="\n"
    )
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    readme.write_text(
        before + START + "\n\n" + "\n".join(table) + "\n\n" + END + after,
        encoding="utf-8",
        newline="\n",
    )
    # The documentation site uses the same chart and guide as the repository.
    repo = ROOT.parents[2]
    website = repo / "guidance_layer/website"
    (website / "public/images/transcription-historical-wer.svg").write_text(
        "\n".join(svg) + "\n", encoding="utf-8", newline="\n"
    )
    body = readme.read_text(encoding="utf-8").split("## Related examples", 1)[0]
    body = body.replace(START, "").replace(END, "")
    body = body.replace("# Transcription evaluation\n\n", "", 1)
    body = body.replace("(images/historical-wer.svg)", "(/images/transcription-historical-wer.svg)")
    base = (
        "https://github.com/GAIK-project/gaik-toolkit/blob/main/"
        "evaluation_layer/eval_methods/transcription_eval/"
    )
    body = re.sub(r"\]\((?!https?://|/)([^)]+)\)", lambda match: "](" + base + match[1] + ")", body)
    front = (
        "---\ntitle: Transcription Evaluation\n"
        "description: Finnish transcription inputs, WER/CER methodology, "
        "raw vs enhanced results and reproducibility limits\n---\n\n"
    )
    (website / "content/docs/evaluation-layer/transcription-eval.mdx").write_text(
        (front + body).rstrip() + "\n", encoding="utf-8", newline="\n"
    )
    print("Updated historical table, chart and documentation page (no inference).")


if __name__ == "__main__":
    main()
