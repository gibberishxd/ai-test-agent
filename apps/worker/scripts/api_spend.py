"""Real Claude API spend so far, from the app's own cost records (run 8).

    cd apps/worker && uv run python scripts/api_spend.py

Every run made with LLM_PROVIDER=claude stores what its calls were charged in `runs.cost_usd`
(the agent's calls, verification and dedup; the benchmark judge is local). The sum over runs
whose provider is `claude` is the API spend; claude-cli runs are charged $0 and left out.
"""

from sqlalchemy import func

from worker.db.models import Run


def api_spend(sessions) -> float:
    with sessions() as session:
        total = (
            session.query(func.coalesce(func.sum(Run.cost_usd), 0.0))
            .filter(Run.provider == "claude")
            .scalar()
        )
        return float(total or 0.0)


def runs_by_provider(sessions) -> list[tuple[str, int, float, float]]:
    with sessions() as session:
        rows = (
            session.query(
                Run.provider,
                func.count(Run.id),
                func.coalesce(func.sum(Run.cost_usd), 0.0),
                func.coalesce(func.sum(Run.estimated_cost_usd), 0.0),
            )
            .group_by(Run.provider)
            .all()
        )
        return [(p or "-", n, float(c), float(e)) for p, n, c, e in rows]


if __name__ == "__main__":
    from worker.config import get_settings
    from worker.db.session import make_engine, make_session_factory

    sessions = make_session_factory(make_engine(get_settings(), admin=True))
    print(f"Claude API spend (runs.provider = 'claude'): ${api_spend(sessions):.4f}")
    for provider, n, charged, estimated in runs_by_provider(sessions):
        print(
            f"  {provider:<12} {n:>4} runs  charged ${charged:.4f}  API-equivalent ${estimated:.4f}"
        )
