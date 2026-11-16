"""Critical flows, measured (run 7, M4).

    cd apps/worker && LLM_PROVIDER=claude-cli CLAUDE_CLI_MODEL=claude-haiku-5-5 DEV_MODE=true \\
        uv run python scripts/flows_measure.py

Two runs on the demo shop (DEMO_URL) in a fresh workspace with three critical flows: run 1
completes them with the agent and saves their scripts; run 2 replays them. Prints, per run and
per journey: status, whether it was replayed without a model, model calls and estimated cost.
The three journeys are plain product journeys written for this measurement, not taken from the
shop's bug list. Stops at once on a claude-cli usage limit.
"""

import json
import sys

from sqlalchemy import func

from worker.config import Settings
from worker.db.models import Flow, FlowResult, Run, Step, Target, Workspace
from worker.db.session import make_engine, make_session_factory
from worker.execute import make_execute
from worker.flows import DEMO_SHOP_FLOWS as SHOP_FLOWS
from worker.llm import make_client
from worker.llm.claude_cli import limit_reached
from worker.runner import process_next
from worker.storage import make_storage

SLUG = "flows-measure"


def fresh_workspace(sessions, settings: Settings):
    with sessions() as session:
        old = session.query(Workspace).filter_by(slug=SLUG).one_or_none()
        if old is not None:
            session.delete(old)
            session.commit()
        workspace = Workspace(name="Flows measurement", slug=SLUG)
        session.add(workspace)
        session.flush()
        target = Target(
            workspace_id=workspace.id, origin=settings.demo_url.rstrip("/"), name="Shop"
        )
        session.add(target)
        session.flush()
        for position, (name, goal) in enumerate(SHOP_FLOWS):
            session.add(
                Flow(
                    workspace_id=workspace.id,
                    target_id=target.id,
                    name=name,
                    goal=goal,
                    position=position,
                )
            )
        session.commit()
        return workspace.id


def one_run(sessions, llm, execute, workspace_id, settings: Settings) -> dict:
    with sessions() as session:
        run = Run(workspace_id=workspace_id, target_url=settings.demo_url, mode="interactive")
        session.add(run)
        session.commit()
        run_id = run.id
    process_next(sessions, llm, execute, only=[str(run_id)])
    with sessions() as session:
        run = session.get(Run, run_id)
        flows = [
            {
                "flow": session.get(Flow, r.flow_id).name,
                "status": r.status,
                "replayed": r.replayed,
                "model_calls": r.model_calls,
                "estimated_cost_usd": round(r.estimated_cost_usd, 4),
                "detail": r.detail,
            }
            for r in session.query(FlowResult)
            .filter_by(run_id=run_id)
            .order_by(FlowResult.created_at)
        ]
        model_steps = (
            session.query(func.count(Step.id))
            .filter(Step.run_id == run_id, Step.model.is_not(None))
            .scalar()
        )
        return {
            "run": str(run_id),
            "status": run.status,
            "error": run.error,
            "seconds": round((run.finished_at - run.started_at).total_seconds())
            if run.finished_at
            else None,
            "steps": run.step_count,
            "model_calls_in_run": model_steps,
            "estimated_cost_usd": round(run.estimated_cost_usd, 4),
            "flows": flows,
            "flow_model_calls": sum(f["model_calls"] for f in flows),
            "flow_estimated_cost_usd": round(sum(f["estimated_cost_usd"] for f in flows), 4),
            "covered": sum(
                f["status"] in ("passed", "replayed", "repaired", "failed") for f in flows
            ),
        }


def main() -> int:
    settings = Settings()
    sessions = make_session_factory(make_engine(settings, admin=True))
    llm = make_client(settings)
    execute = make_execute(settings, make_storage(settings))
    workspace_id = fresh_workspace(sessions, settings)
    results = []
    for label in ("run 1 (learn)", "run 2 (replay)"):
        result = one_run(sessions, llm, execute, workspace_id, settings)
        result["label"] = label
        results.append(result)
        print(json.dumps(result, indent=2), flush=True)
        if limit_reached():
            print(f"stopped: {limit_reached()}", flush=True)
            break
    print(json.dumps({"summary": results}, indent=None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
