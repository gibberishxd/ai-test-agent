"""The first real Claude API run (run 8, N1): one short Haiku run on the demo shop.

    cd apps/worker && LLM_PROVIDER=claude AGENT_MODEL=claude-haiku-5-5 \\
        CHEAP_MODEL=claude-haiku-5-5 DEV_MODE=true MAX_STEPS=12 MAX_RUN_SECONDS=300 \\
        MAX_RUN_COST_USD=0.5 uv run python scripts/api_smoke.py

Checks, per step: a tool call came back, cache reads appear after the first steps, and the
recorded cost equals the token counts at list price (llm/pricing.py). Refuses to start unless
the provider is `claude` and the API spend recorded so far (scripts/api_spend.py) plus this
run's cap stays within API_BUDGET_USD (default $4). The key is never printed.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from api_spend import api_spend  # noqa: E402

from worker.config import get_settings  # noqa: E402
from worker.db.models import Run, Step, Workspace  # noqa: E402
from worker.db.session import make_engine, make_session_factory  # noqa: E402
from worker.execute import make_execute  # noqa: E402
from worker.llm import Usage, make_client  # noqa: E402
from worker.llm.pricing import cost_usd  # noqa: E402
from worker.main import setup_logging  # noqa: E402
from worker.runner import process_next  # noqa: E402
from worker.storage import make_storage  # noqa: E402

SLUG = "api-smoke"
BUDGET = float(os.environ.get("API_BUDGET_USD", "4"))


def main() -> None:
    settings = get_settings()
    setup_logging((settings.anthropic_api_key.get_secret_value(),))
    if settings.provider() != "claude":
        raise SystemExit("api_smoke: LLM_PROVIDER must be claude")
    sessions = make_session_factory(make_engine(settings, admin=True))
    spent = api_spend(sessions)
    if spent + settings.max_run_cost_usd > BUDGET:
        raise SystemExit(
            f"api_smoke: ${spent:.4f} spent + ${settings.max_run_cost_usd} cap > ${BUDGET}"
        )
    print(
        f"API spend before: ${spent:.4f} "
        f"(budget ${BUDGET}, this run's cap ${settings.max_run_cost_usd})"
    )
    llm = make_client(settings)
    execute = make_execute(settings, make_storage(settings))
    with sessions() as session:
        workspace = session.query(Workspace).filter_by(slug=SLUG).one_or_none()
        if workspace is None:
            workspace = Workspace(name="API smoke test", slug=SLUG)
            session.add(workspace)
            session.flush()
        run = Run(workspace_id=workspace.id, target_url=settings.demo_url, mode="interactive")
        session.add(run)
        session.commit()
        run_id = run.id
    process_next(sessions, llm, execute, only=[str(run_id)])
    report(sessions, run_id)
    print(f"API spend after: ${api_spend(sessions):.4f}")


def report(sessions, run_id) -> None:
    with sessions() as session:
        run = session.get(Run, run_id)
        steps = session.query(Step).filter_by(run_id=run_id).order_by(Step.index).all()
        print(f"\nrun {run.id} status={run.status} provider={run.provider} model={run.model}")
        print(f"error: {run.error}")
        header = "idx action           model              uncached  c.read c.write   out   cost$"
        print(header)
        recomputed = 0.0
        for s in steps:
            uncached = s.input_tokens - s.cache_read_tokens - s.cache_write_tokens
            usage = Usage(
                model=s.model or "",
                input_tokens=uncached,
                output_tokens=s.output_tokens,
                cache_read_tokens=s.cache_read_tokens,
                cache_write_tokens=s.cache_write_tokens,
            )
            again = cost_usd(s.model or "", usage) if s.model else 0.0
            recomputed += again
            flag = "" if abs(again - s.cost_usd) < 1e-9 else f"  MISMATCH {again:.6f}"
            print(
                f"{s.index:>3} {s.action[:16]:<16} {str(s.model)[:18]:<18} {uncached:>8}"
                f" {s.cache_read_tokens:>7} {s.cache_write_tokens:>7} {s.output_tokens:>5}"
                f" {s.cost_usd:.5f}{flag}"
            )
        model_steps = [s for s in steps if s.model]
        with_reads = [s.index for s in model_steps if s.cache_read_tokens > 0]
        print(f"\nsteps {len(steps)}, with a model call {len(model_steps)}")
        print(f"steps with cache reads: {len(with_reads)} (first at {with_reads[:1]})")
        print(
            f"run cost_usd (charged) ${run.cost_usd:.5f}; estimated ${run.estimated_cost_usd:.5f}"
        )
        print(f"steps' cost recomputed from tokens ${recomputed:.5f}")
        print(
            f"tokens: in {run.input_tokens} (cache read {run.cache_read_tokens}, "
            f"write {run.cache_write_tokens}), out {run.output_tokens}"
        )
        bugs = run.bugs
        print(f"bugs: {len(bugs)}")
        for b in bugs:
            print(f"  [{b.status}] {b.title}")


if __name__ == "__main__":
    main()
