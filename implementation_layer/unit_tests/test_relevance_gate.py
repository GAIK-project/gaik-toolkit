"""RelevanceGate: the floor, the "no opinion" case, and calibration honesty."""

from __future__ import annotations

import pytest
from gaik.software_components.RAG.relevance_gate import RelevanceGate


class TestTheFloor:
    def test_a_close_match_is_answerable_and_a_far_one_is_not(self):
        gate = RelevanceGate(floor=0.60)
        assert gate.is_answerable([0.31, 0.44, 0.58]) is True
        assert gate.is_answerable([0.71, 0.80, 0.86]) is False

    def test_result_count_does_not_enter_into_it(self):
        """The defect this component exists for.

        Measured on a real corpus, a gibberish query returned *more* rows than a
        real domain question. Anything that reasons from `len(results)` reproduces
        that mistake.
        """
        gate = RelevanceGate(floor=0.60)
        many_far = [0.70] * 24
        few_close = [0.35] * 2
        assert gate.is_answerable(many_far) is False
        assert gate.is_answerable(few_close) is True

    def test_empty_results_are_never_answerable(self):
        assert RelevanceGate(floor=0.60).is_answerable([]) is False

    def test_similarity_scores_run_the_other_way(self):
        gate = RelevanceGate(floor=0.40, lower_is_better=False)
        assert gate.is_answerable([0.62]) is True
        assert gate.is_answerable([0.18]) is False


class TestNoOpinion:
    def test_missing_scores_pass_rather_than_fail(self):
        """`None` means nothing was searched by vector, not that it was irrelevant.

        A keyword-only search has no distances at all. Treating that as "far away"
        turns the gate into a permanent refusal on exactly the mode that has no
        opinion to offer.
        """
        gate = RelevanceGate(floor=0.60)
        assert gate.best([None, None]) is None
        assert gate.passes(None) is True
        assert gate.is_answerable([None, None]) is True

    def test_a_mix_judges_on_the_scores_that_exist(self):
        gate = RelevanceGate(floor=0.60)
        assert gate.best([None, 0.42, None]) == pytest.approx(0.42)
        assert gate.is_answerable([None, 0.42]) is True

    def test_results_may_be_any_shape_given_a_key(self):
        gate = RelevanceGate(floor=0.60)
        hits = [("doc-a", 0.81), ("doc-b", 0.39)]
        assert gate.best(hits, key=lambda h: h[1]) == pytest.approx(0.39)
        assert gate.is_answerable(hits, key=lambda h: h[1]) is True

    def test_a_generator_is_consumed_once_and_still_judged(self):
        gate = RelevanceGate(floor=0.60)
        assert gate.is_answerable(x for x in [0.80, 0.30]) is True
        assert gate.is_answerable(x for x in []) is False


class TestFilter:
    def test_filter_trims_individual_results_keeping_order(self):
        gate = RelevanceGate(floor=0.60)
        assert gate.filter([0.20, 0.90, 0.50]) == [0.20, 0.50]

    def test_filter_keeps_unscored_results(self):
        gate = RelevanceGate(floor=0.60)
        assert gate.filter([0.20, None, 0.90]) == [0.20, None]


class TestCalibration:
    def test_a_clean_gap_yields_a_floor_between_the_populations(self):
        reading = RelevanceGate.calibrate(
            answerable=[0.264, 0.41, 0.562],
            unanswerable=[0.637, 0.72, 0.866],
        )
        assert reading.separated is True
        assert reading.worst_answerable == pytest.approx(0.562)
        assert reading.best_unanswerable == pytest.approx(0.637)
        assert reading.floor == pytest.approx(0.5995)
        assert reading.margin == pytest.approx(0.075)

    def test_overlapping_populations_produce_no_floor_rather_than_a_compromise(self):
        """The answer that stops you shipping a meaningless threshold.

        Splitting the difference between two overlapping populations produces a
        number that looks like a measurement and rejects real queries.
        """
        reading = RelevanceGate.calibrate(
            answerable=[0.30, 0.71],
            unanswerable=[0.62, 0.88],
        )
        assert reading.separated is False
        assert reading.floor is None
        assert reading.margin < 0
        assert "OVERLAPPING" in str(reading)

    def test_similarity_direction_is_honoured(self):
        reading = RelevanceGate.calibrate(
            answerable=[0.80, 0.65],
            unanswerable=[0.40, 0.22],
            lower_is_better=False,
        )
        assert reading.separated is True
        assert reading.floor == pytest.approx(0.525)

    def test_the_summary_points_the_right_way_for_similarities(self):
        """The skill tells users to print() the reading; with similarities the
        comparisons used to point the distance way and contradict the numbers."""
        reading = RelevanceGate.calibrate(
            answerable=[0.80, 0.65],
            unanswerable=[0.40, 0.22],
            lower_is_better=False,
        )
        assert "answerable ≥ 0.650" in str(reading)
        assert "unanswerable ≤ 0.400" in str(reading)

    def test_an_empty_population_is_refused(self):
        with pytest.raises(ValueError, match="both populations"):
            RelevanceGate.calibrate(answerable=[0.3], unanswerable=[])

    def test_the_summary_reports_the_numbers_it_read(self):
        reading = RelevanceGate.calibrate(answerable=[0.5], unanswerable=[0.7])
        assert "separated" in str(reading)
        assert "0.600" in str(reading)
