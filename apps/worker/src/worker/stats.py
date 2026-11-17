"""Confidence intervals for benchmark recall (run 8, N3).

A benchmark result is a handful of runs, so one bug more or less moves recall by many points.
Two intervals say how much the number could move with more runs:

- **Wilson 95% interval over bug×run slots.** Each (judgement bug, buggy run) pair is a slot,
  found or not: k of n. Wilson's interval stays inside [0, 1] and behaves for small n and for
  k = 0 or k = n, where the textbook p ± 1.96·sqrt(p(1-p)/n) breaks. It treats slots as
  independent, which they aren't quite (one good run finds several bugs), so it is the narrower
  of the two.
- **Bootstrap 95% interval over runs.** Resample the runs with replacement, recompute the mean
  per-run recall, many times; the 2.5th and 97.5th percentiles. It keeps each run's bugs
  together, so a run-to-run difference in how well the agent explored shows up. With 2-3 runs it
  can only take a few values; it needs 8 or more to mean much.

Two setups differ beyond noise only if their intervals don't overlap (a rough, conservative
reading; we don't run significance tests on samples this small).
"""

import math
import random
from collections.abc import Sequence

Z95 = 1.959963984540054
BOOTSTRAP_ITERATIONS = 2000
SEED = 8  # fixed, so the same runs always give the same interval


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k successes out of n (0..1). (0, 1) when n is 0."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_mean(
    values: Sequence[float],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = SEED,
    level: float = 0.95,
) -> tuple[float, float]:
    """Percentile bootstrap interval of the mean of `values` (one value per run)."""
    if not values:
        return 0.0, 1.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(iterations))
    tail = (1 - level) / 2
    low = means[int(math.floor(tail * (iterations - 1)))]
    high = means[int(math.ceil((1 - tail) * (iterations - 1)))]
    return low, high


def recall_interval(found_per_run: Sequence[set[int]], bug_ids: set[int]) -> dict:
    """Recall over `bug_ids` with both intervals, from the bugs each buggy run found.

    {"k", "n", "recall", "wilson": [lo, hi], "bootstrap": [lo, hi]}; recall = k / n, which
    equals the mean per-run recall the benchmark reports."""
    runs = len(found_per_run)
    n = len(bug_ids) * runs
    k = sum(len(found & bug_ids) for found in found_per_run)
    per_run = [len(found & bug_ids) / len(bug_ids) for found in found_per_run] if bug_ids else []
    return {
        "k": k,
        "n": n,
        "recall": k / n if n else 0.0,
        "wilson": list(wilson(k, n)),
        "bootstrap": list(bootstrap_mean(per_run)),
    }


def overlap(a: Sequence[float], b: Sequence[float]) -> bool:
    """Do two intervals overlap? (Then the difference between them is within noise.)"""
    return a[0] <= b[1] and b[0] <= a[1]


def fmt(interval: dict) -> str:
    """'33% (9/27; Wilson 19–52%, bootstrap 22–44%)'."""
    lo, hi = interval["wilson"]
    blo, bhi = interval["bootstrap"]
    return (
        f"{interval['recall']:.0%} ({interval['k']}/{interval['n']}; "
        f"Wilson {lo:.0%}–{hi:.0%}, bootstrap {blo:.0%}–{bhi:.0%})"
    )
