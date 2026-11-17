"""95% intervals on recall for saved benchmark results (run 8, N3).

    cd apps/worker && uv run python scripts/intervals.py                 # every v2 result
    cd apps/worker && uv run python scripts/intervals.py e92d2c6b 2f9e   # these results
    cd apps/worker && uv run python scripts/intervals.py --pool a1b2 c3d4  # one pooled line

AI-only and all-bugs recall per result, for the shop and the holdout, with a Wilson interval
over bug×run slots and a bootstrap interval over runs (worker/stats.py). Results saved before
run 8 have no intervals stored; they are computed here from their saved decisions.
"""

import argparse

from sqlalchemy import String, cast

from worker.benchmark import HOLDOUT_BUGS_JSON, intervals_from_details, load_planted
from worker.config import get_settings
from worker.db.models import BenchmarkResult
from worker.db.session import make_engine, make_session_factory
from worker.stats import fmt


def rows(session, prefixes: list[str]):
    query = session.query(BenchmarkResult)
    if prefixes:
        found = []
        for prefix in prefixes:
            found += query.filter(cast(BenchmarkResult.id, String).like(f"{prefix}%")).all()
        return found
    return query.filter_by(benchmark_version="v2").order_by(BenchmarkResult.created_at).all()


def label(r) -> str:
    return f"{str(r.id)[:8]} {r.provider}·{r.model} {r.git_commit} {r.created_at:%Y-%m-%d}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="*", help="result id prefixes (default: every v2)")
    parser.add_argument("--pool", action="store_true", help="pool the given results' runs")
    args = parser.parse_args()
    sessions = make_session_factory(make_engine(get_settings(), admin=True))
    shop, holdout = load_planted(), load_planted(HOLDOUT_BUGS_JSON)
    with sessions() as session:
        results = rows(session, args.results)
        groups = [results] if args.pool else [[r] for r in results]
        for group in groups:
            details = [r.details or {} for r in group]
            name = " + ".join(label(r) for r in group)
            print(name + ("  (pooled)" if args.pool else ""))
            for which, planted in (("shop", shop), ("holdout", holdout)):
                iv = intervals_from_details(details, planted, which)
                if iv["ai_recall"]["n"] == 0:
                    continue
                print(f"  {which:<8} AI-only {fmt(iv['ai_recall'])}")
                print(f"  {'':<8} all     {fmt(iv['recall'])}")


if __name__ == "__main__":
    main()
