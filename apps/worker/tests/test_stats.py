"""Run 8, N3: confidence intervals on benchmark recall."""

import pytest

from worker.stats import bootstrap_mean, fmt, overlap, recall_interval, wilson


def test_wilson_matches_the_published_values():
    # Reference values (Newcombe 1998, method 3): 81 of 263 → 0.2553–0.3662.
    lo, hi = wilson(81, 263)
    assert lo == pytest.approx(0.2553, abs=5e-4) and hi == pytest.approx(0.3662, abs=5e-4)


def test_wilson_stays_inside_zero_and_one_at_the_edges():
    lo, hi = wilson(0, 8)
    assert lo == 0.0 and 0.3 < hi < 0.4  # 0 of 8 found: up to ~32% is still plausible
    lo, hi = wilson(8, 8)
    assert hi == 1.0 and 0.6 < lo < 0.7


def test_wilson_without_slots_says_nothing():
    assert wilson(0, 0) == (0.0, 1.0)


def test_one_bug_more_on_eight_slots_is_inside_the_noise():
    # Run 7's holdout: 5 of 8 (62%) vs 6 of 8 (75%), the "12 points" difference.
    assert overlap(wilson(5, 8), wilson(6, 8))


def test_bootstrap_is_reproducible_and_brackets_the_mean():
    values = [0.2, 0.4, 0.3, 0.5, 0.1, 0.3, 0.4, 0.2]
    first = bootstrap_mean(values)
    assert first == bootstrap_mean(values)  # fixed seed
    mean = sum(values) / len(values)
    assert first[0] <= mean <= first[1]
    assert first[1] - first[0] < 0.25


def test_bootstrap_of_identical_runs_has_no_width():
    assert bootstrap_mean([0.5, 0.5, 0.5]) == (0.5, 0.5)


def test_recall_interval_counts_bug_run_slots():
    ai = {5, 6, 7}
    found = [{5, 6, 1}, {5}, set()]  # bug 1 is deterministic: not in the set
    result = recall_interval(found, ai)
    assert (result["k"], result["n"]) == (3, 9)
    assert result["recall"] == pytest.approx(1 / 3)
    lo, hi = result["wilson"]
    assert lo < 1 / 3 < hi
    assert "33% (3/9; Wilson" in fmt(result)


def test_overlap():
    assert overlap((0.1, 0.4), (0.3, 0.6))
    assert not overlap((0.1, 0.2), (0.3, 0.6))
