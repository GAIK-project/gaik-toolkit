"""
Batch evaluation comparing original vs enhanced transcripts.

Computes WER, CER, and Spelling Error Rate for both versions.
"""

import sys
from pathlib import Path

import jiwer
from rapidfuzz.distance import Levenshtein


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

def evaluate_batch(reference_dir: str, original_dir: str, enhanced_dir: str):
    """
    Evaluate original and enhanced transcripts against ground truth.

    Args:
        reference_dir: Directory with ground truth transcripts
        original_dir: Directory with original ASR transcripts
        enhanced_dir: Directory with GPT-enhanced transcripts
    """
    ref_path = Path(reference_dir)
    orig_path = Path(original_dir)
    enh_path = Path(enhanced_dir)

    if not ref_path.exists():
        raise FileNotFoundError(f"Reference directory not found: {ref_path}")
    if not orig_path.exists():
        raise FileNotFoundError(f"Original directory not found: {orig_path}")
    if not enh_path.exists():
        raise FileNotFoundError(f"Enhanced directory not found: {enh_path}")

    # Collect original stats
    orig_total_subs = 0
    orig_total_dels = 0
    orig_total_ins = 0
    orig_total_ref_words = 0
    orig_total_spelling_errors = 0
    orig_total_char_subs = 0
    orig_total_char_dels = 0
    orig_total_char_ins = 0
    orig_total_ref_chars = 0

    # Collect enhanced stats
    enh_total_subs = 0
    enh_total_dels = 0
    enh_total_ins = 0
    enh_total_ref_words = 0
    enh_total_spelling_errors = 0
    enh_total_char_subs = 0
    enh_total_char_dels = 0
    enh_total_char_ins = 0
    enh_total_ref_chars = 0

    evaluated = 0
    improved = 0
    degraded = 0
    unchanged = 0

    print("=" * 80)
    print("EVALUATING ORIGINAL VS ENHANCED TRANSCRIPTS")
    print("=" * 80)
    print()

    for ref_file in sorted(ref_path.glob("*.txt")):
        stem = ref_file.stem
        orig_file = orig_path / ref_file.name
        enh_file = enh_path / ref_file.name

        if not orig_file.exists():
            print(f"WARNING: Missing original: {orig_file.name}")
            continue

        if not enh_file.exists():
            print(f"WARNING: Missing enhanced: {enh_file.name}")
            continue

        # Read texts
        ref_text = ref_file.read_text(encoding="utf-8")
        orig_text = orig_file.read_text(encoding="utf-8")
        enh_text = enh_file.read_text(encoding="utf-8")

        # Evaluate original
        orig_output, orig_cer_output = _evaluate_texts(ref_text, orig_text)
        orig_wer = orig_output.wer

        # Evaluate enhanced
        enh_output, enh_cer_output = _evaluate_texts(ref_text, enh_text)
        enh_wer = enh_output.wer

        # Track stats
        orig_total_subs += orig_output.substitutions
        orig_total_dels += orig_output.deletions
        orig_total_ins += orig_output.insertions
        orig_total_ref_words += orig_output.hits + orig_output.substitutions + orig_output.deletions
        orig_total_spelling_errors += _spelling_error_count(orig_output)
        orig_total_char_subs += orig_cer_output.substitutions
        orig_total_char_dels += orig_cer_output.deletions
        orig_total_char_ins += orig_cer_output.insertions
        orig_total_ref_chars += orig_cer_output.hits + orig_cer_output.substitutions + orig_cer_output.deletions

        enh_total_subs += enh_output.substitutions
        enh_total_dels += enh_output.deletions
        enh_total_ins += enh_output.insertions
        enh_total_ref_words += enh_output.hits + enh_output.substitutions + enh_output.deletions
        enh_total_spelling_errors += _spelling_error_count(enh_output)
        enh_total_char_subs += enh_cer_output.substitutions
        enh_total_char_dels += enh_cer_output.deletions
        enh_total_char_ins += enh_cer_output.insertions
        enh_total_ref_chars += enh_cer_output.hits + enh_cer_output.substitutions + enh_cer_output.deletions

        evaluated += 1

        # Determine improvement/degradation
        diff = orig_wer - enh_wer
        if diff > 0.001:  # Improved
            status = "IMPROVED"
            improved += 1
        elif diff < -0.001:  # Degraded
            status = "DEGRADED"
            degraded += 1
        else:  # Unchanged
            status = "SAME"
            unchanged += 1

        print(f"{stem:40s} | Orig: {orig_wer:6.2%} | Enh: {enh_wer:6.2%} | Delta: {diff:+.2%} | {status}")

    if evaluated == 0:
        print("No files evaluated.")
        return

    # Compute aggregate metrics
    orig_wer = (orig_total_subs + orig_total_dels + orig_total_ins) / orig_total_ref_words
    enh_wer = (enh_total_subs + enh_total_dels + enh_total_ins) / enh_total_ref_words

    orig_cer = (orig_total_char_subs + orig_total_char_dels + orig_total_char_ins) / orig_total_ref_chars if orig_total_ref_chars else 0
    enh_cer = (enh_total_char_subs + enh_total_char_dels + enh_total_char_ins) / enh_total_ref_chars if enh_total_ref_chars else 0

    orig_spelling_rate = orig_total_spelling_errors / orig_total_ref_words
    enh_spelling_rate = enh_total_spelling_errors / enh_total_ref_words

    orig_sub_rate = orig_total_subs / orig_total_ref_words
    enh_sub_rate = enh_total_subs / enh_total_ref_words

    orig_del_rate = orig_total_dels / orig_total_ref_words
    enh_del_rate = enh_total_dels / enh_total_ref_words

    orig_ins_rate = orig_total_ins / orig_total_ref_words
    enh_ins_rate = enh_total_ins / enh_total_ref_words

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Files evaluated:     {evaluated}")
    print(f"  Improved:          {improved}")
    print(f"  Degraded:          {degraded}")
    print(f"  Unchanged:         {unchanged}")
    print()

    print("=" * 80)
    print("AGGREGATE METRICS")
    print("=" * 80)
    print(f"{'Metric':<30s} | {'Original':>10s} | {'Enhanced':>10s} | {'Change':>10s}")
    print("-" * 80)
    print(f"{'Word Error Rate (WER)':<30s} | {orig_wer:>10.2%} | {enh_wer:>10.2%} | {(enh_wer - orig_wer):>+10.2%}")
    print(f"{'Character Error Rate (CER)':<30s} | {orig_cer:>10.2%} | {enh_cer:>10.2%} | {(enh_cer - orig_cer):>+10.2%}")
    print(f"{'Spelling Error Rate':<30s} | {orig_spelling_rate:>10.2%} | {enh_spelling_rate:>10.2%} | {(enh_spelling_rate - orig_spelling_rate):>+10.2%}")
    print(f"{'Substitution Rate':<30s} | {orig_sub_rate:>10.2%} | {enh_sub_rate:>10.2%} | {(enh_sub_rate - orig_sub_rate):>+10.2%}")
    print(f"{'Deletion Rate':<30s} | {orig_del_rate:>10.2%} | {enh_del_rate:>10.2%} | {(enh_del_rate - orig_del_rate):>+10.2%}")
    print(f"{'Insertion Rate':<30s} | {orig_ins_rate:>10.2%} | {enh_ins_rate:>10.2%} | {(enh_ins_rate - orig_ins_rate):>+10.2%}")
    print("=" * 80)

    if enh_wer < orig_wer:
        improvement = (orig_wer - enh_wer) * 100
        print(f"\n>>> Overall WER improved by {improvement:.2f} percentage points!")
    elif enh_wer > orig_wer:
        degradation = (enh_wer - orig_wer) * 100
        print(f"\n>>> Overall WER degraded by {degradation:.2f} percentage points.")
    else:
        print("\n>>> Overall WER unchanged.")

def main():
    if len(sys.argv) != 4:
        print("Usage: python eval_enhanced.py <reference_dir> <original_dir> <enhanced_dir>")
        print()
        print("Example:")
        print('  python eval_enhanced.py "C:\\Users\\h02317\\Downloads\\transcripts" transcripts enhanced')
        sys.exit(1)

    evaluate_batch(sys.argv[1], sys.argv[2], sys.argv[3])

if __name__ == "__main__":
    main()

