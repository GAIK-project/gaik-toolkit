"""
Compare hypothesis transcripts against reference transcripts.

Generates per-file evaluation reports including WER and other metrics and
side-by-side aligned output.
"""

import sys
from pathlib import Path

import jiwer
from rapidfuzz.distance import Levenshtein

MAX_SIDE_BY_SIDE_LINES = 120
MAX_SIDE_BY_SIDE_SENTENCES = 1
MAX_TOKENS_PER_LINE = 18


def _build_transform():
    return jiwer.Compose(
        [
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.ReduceToListOfListOfWords(),
        ]
    )


def _build_char_transform():
    return jiwer.Compose(
        [
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.ReduceToListOfListOfChars(),
        ]
    )


def _is_spelling_error(ref_word, hyp_word, max_normalized_distance=0.4):
    max_len = max(len(ref_word), len(hyp_word))
    if max_len == 0:
        return False
    distance = Levenshtein.distance(ref_word, hyp_word)
    normalized_distance = distance / max_len
    return normalized_distance <= max_normalized_distance


def _build_aligned_tokens(ref_words, hyp_words, chunks):
    aligned_ref = []
    aligned_hyp = []

    for chunk in chunks:
        ref_span = ref_words[chunk.ref_start_idx : chunk.ref_end_idx]
        hyp_span = hyp_words[chunk.hyp_start_idx : chunk.hyp_end_idx]

        if chunk.type == "equal":
            for r_word, h_word in zip(ref_span, hyp_span):
                aligned_ref.append(r_word)
                aligned_hyp.append(h_word)
        elif chunk.type == "substitute":
            max_len = max(len(ref_span), len(hyp_span))
            for i in range(max_len):
                r_word = ref_span[i] if i < len(ref_span) else ""
                h_word = hyp_span[i] if i < len(hyp_span) else ""
                if r_word and h_word:
                    aligned_ref.append(r_word)
                    if _is_spelling_error(r_word, h_word):
                        aligned_hyp.append(f"{h_word}[S,C:{r_word}]")
                    else:
                        aligned_hyp.append(f"{h_word}[S:{r_word}]")
                elif h_word:
                    aligned_ref.append("")
                    aligned_hyp.append(f"{h_word}[I]")
                else:
                    aligned_ref.append(r_word)
                    aligned_hyp.append(f"[D:{r_word}]")
        elif chunk.type == "insert":
            for h_word in hyp_span:
                aligned_ref.append("")
                aligned_hyp.append(f"{h_word}[I]")
        elif chunk.type == "delete":
            for r_word in ref_span:
                aligned_ref.append(r_word)
                aligned_hyp.append(f"[D:{r_word}]")

    return aligned_ref, aligned_hyp


def _spelling_error_count(output, max_normalized_distance=0.4):
    spelling_errors = 0
    for ref_words_sent, hyp_words_sent, chunks in zip(
        output.references, output.hypotheses, output.alignments
    ):
        for chunk in chunks:
            if chunk.type != "substitute":
                continue
            ref_span = ref_words_sent[chunk.ref_start_idx : chunk.ref_end_idx]
            hyp_span = hyp_words_sent[chunk.hyp_start_idx : chunk.hyp_end_idx]
            pair_len = min(len(ref_span), len(hyp_span))
            for i in range(pair_len):
                ref_word = ref_span[i]
                hyp_word = hyp_span[i]
                max_len = max(len(ref_word), len(hyp_word))
                if max_len == 0:
                    continue
                if _is_spelling_error(
                    ref_word, hyp_word, max_normalized_distance=max_normalized_distance
                ):
                    spelling_errors += 1

    return spelling_errors


def _format_side_by_side(
    output,
    max_tokens_per_line=MAX_TOKENS_PER_LINE,
    max_sentences=MAX_SIDE_BY_SIDE_SENTENCES,
    max_lines=MAX_SIDE_BY_SIDE_LINES,
):
    lines = []
    lines_printed = 0

    for sent_idx, (ref_words, hyp_words, chunks) in enumerate(
        zip(output.references, output.hypotheses, output.alignments)
    ):
        if max_sentences is not None and sent_idx >= max_sentences:
            break

        aligned_ref, aligned_hyp = _build_aligned_tokens(ref_words, hyp_words, chunks)

        for start in range(0, len(aligned_ref), max_tokens_per_line):
            ref_slice = aligned_ref[start : start + max_tokens_per_line]
            hyp_slice = aligned_hyp[start : start + max_tokens_per_line]
            widths = [max(len(r), len(h)) for r, h in zip(ref_slice, hyp_slice)]

            ref_line = "REF: " + " ".join(
                token.ljust(width) for token, width in zip(ref_slice, widths)
            )
            hyp_line = "HYP: " + " ".join(
                token.ljust(width) for token, width in zip(hyp_slice, widths)
            )

            lines.append(ref_line)
            lines.append(hyp_line)
            lines.append("")

            lines_printed += 2
            if max_lines is not None and lines_printed >= max_lines:
                lines.append("... [side-by-side truncated] ...")
                return lines

    return lines


def _evaluate_texts(reference_text, hypothesis_text):
    word_transform = _build_transform()
    char_transform = _build_char_transform()
    word_output = jiwer.process_words(
        reference_text,
        hypothesis_text,
        reference_transform=word_transform,
        hypothesis_transform=word_transform,
    )
    char_output = jiwer.process_characters(
        reference_text,
        hypothesis_text,
        reference_transform=char_transform,
        hypothesis_transform=char_transform,
    )
    return word_output, char_output


def _format_report(
    output, cer_output=None, max_alignment_chars=2000, max_side_by_side_lines=120
):
    ref_words = output.hits + output.substitutions + output.deletions
    if ref_words:
        sub_rate = output.substitutions / ref_words
        del_rate = output.deletions / ref_words
        ins_rate = output.insertions / ref_words
    else:
        sub_rate = 0.0
        del_rate = 0.0
        ins_rate = 0.0
    spelling_errors = _spelling_error_count(output)
    spelling_rate = spelling_errors / ref_words if ref_words else 0.0

    lines = []
    lines.append("=" * 50)
    lines.append("TRANSCRIPTION ACCURACY REPORT")
    lines.append("=" * 50)
    lines.append(f"Word Error Rate (WER):      {output.wer:.2%}")
    if cer_output is not None:
        lines.append(f"Character Error Rate (CER): {cer_output.cer:.2%}")
    lines.append(f"Spelling Error Rate:        {spelling_rate:.2%}")
    lines.append(f"Substitution Rate:          {sub_rate:.2%}")
    lines.append(f"Deletion Rate:              {del_rate:.2%}")
    lines.append(f"Insertion Rate:             {ins_rate:.2%}")

    lines.append("-" * 50)
    lines.append(f"Total words in reference:   {ref_words}")
    lines.append(f"Correct words:              {output.hits}")
    lines.append(f"Substitutions:              {output.substitutions}")
    lines.append(f"Insertions:                 {output.insertions}")
    lines.append(f"Deletions:                  {output.deletions}")
    lines.append("=" * 50)

    lines.append("")
    lines.append("SIDE-BY-SIDE (marked hypothesis, truncated):")
    lines.append("")
    lines.extend(_format_side_by_side(output, max_lines=max_side_by_side_lines))

    return "\n".join(lines)


def compare_folders(ref_dir, hyp_dir, out_dir):
    ref_path = Path(ref_dir)
    hyp_path = Path(hyp_dir)
    out_path = Path(out_dir)

    if not hyp_path.exists():
        raise FileNotFoundError(f"Hypothesis folder not found: {hyp_path}")
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference folder not found: {ref_path}")

    out_path.mkdir(parents=True, exist_ok=True)

    ref_files = sorted(ref_path.glob("*.txt"))
    if not ref_files:
        print(f"No .txt files found in {ref_path}")
        return

    total_subs = 0
    total_dels = 0
    total_ins = 0
    total_ref_words = 0
    total_spelling_errors = 0
    total_char_subs = 0
    total_char_dels = 0
    total_char_ins = 0
    total_ref_chars = 0
    evaluated = 0

    for ref_file in ref_files:
        hyp_file = hyp_path / ref_file.name
        if not hyp_file.exists():
            print(f"Missing hypothesis for {ref_file.name}")
            continue

        reference_text = ref_file.read_text(encoding="utf-8")
        hypothesis_text = hyp_file.read_text(encoding="utf-8")
        output, cer_output = _evaluate_texts(reference_text, hypothesis_text)
        report = _format_report(output, cer_output)

        out_file = out_path / f"{ref_file.stem}_side_by_side.txt"
        out_file.write_text(report, encoding="utf-8")
        print(f"Saved: {out_file}")

        total_subs += output.substitutions
        total_dels += output.deletions
        total_ins += output.insertions
        total_ref_words += output.hits + output.substitutions + output.deletions
        total_spelling_errors += _spelling_error_count(output)
        total_char_subs += cer_output.substitutions
        total_char_dels += cer_output.deletions
        total_char_ins += cer_output.insertions
        total_ref_chars += cer_output.hits + cer_output.substitutions + cer_output.deletions
        evaluated += 1

    if evaluated and total_ref_words:
        print("")
        print("AVERAGE STATISTICS")
        wer = (total_subs + total_dels + total_ins) / total_ref_words
        sub_rate = total_subs / total_ref_words
        del_rate = total_dels / total_ref_words
        ins_rate = total_ins / total_ref_words
        spelling_rate = total_spelling_errors / total_ref_words
        print(f"Word Error Rate (WER):      {wer:.2%}")
        if total_ref_chars:
            cer = (total_char_subs + total_char_dels + total_char_ins) / total_ref_chars
            print(f"Character Error Rate (CER): {cer:.2%}")
        print(f"Spelling Error Rate:        {spelling_rate:.2%}")
        print(f"Substitution Rate:          {sub_rate:.2%}")
        print(f"Deletion Rate:              {del_rate:.2%}")
        print(f"Insertion Rate:             {ins_rate:.2%}")


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python side_by_side_compare.py "
            "<reference_folder> <hypothesis_folder> <output_folder>"
        )
        sys.exit(1)

    compare_folders(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    main()
