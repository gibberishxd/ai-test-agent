"""The benchmark: how good is the agent, measured against the demo shop's planted bugs.

`uv run worker bench` (or `npm run bench`) runs the agent N times on the buggy shop and once on
the clean shop, matches every reported bug to apps/demo/bugs.json, and prints and stores:
recall (share of planted bugs found), precision (share of reports that were real planted bugs),
false alarms (reports on the clean shop, where every report is wrong), average cost and
duration, plus provider, model and git commit.

Matching a report to a planted bug: the cheap model judges whether the report describes one of
the bugs planted on its page; if none fits, it is asked again with every planted bug. Every
decision is saved so a human can spot-check it.
"""

import json
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.orm import Session, sessionmaker

from worker.config import REPO_ROOT
from worker.db.models import BenchmarkResult, Bug, Run, Workspace
from worker.llm import LLMClient
from worker.queue import BENCHMARK_SLUG, FINAL
from worker.stats import fmt, recall_interval
from worker.verify import parse_json_object

BUGS_JSON = REPO_ROOT / "apps" / "demo" / "bugs.json"
# Which version of the demo apps a result was measured on. Bump it whenever the apps change in a
# way that can move scores, so old and new results are never compared as if they were the same.
#   v1: runs 1-6.
#   v2 (run 7): four unplanted behaviours run 6's agents reported fixed in both builds: the
#       profile's recent orders, a double-clicked "Add to cart", and the holdout's past dates and
#       dates outside a room's availability.
BENCHMARK_VERSION = "v2"
# The holdout app: same kinds of bugs, different specifics. Never tune prompts against it.
HOLDOUT_BUGS_JSON = REPO_ROOT / "apps" / "demo2" / "bugs.json"

MATCH_SYSTEM = """You match bug reports from an automated tester to a list of known, planted \
bugs. Decide which known bug (if any) the report describes. The report must describe the same \
underlying problem, not just the same page. Answer with only JSON:
{"match": <known bug id or null>, "reason": "one sentence"}"""


@dataclass(frozen=True)
class PlantedBug:
    id: int
    page: str
    title: str
    description: str
    # "deterministic": the free checks can find it. "agent": it needs judgement.
    detection: str = "agent"


# Stages where a report was thrown away (a duplicate isn't: its original still counts).
DISCARD_STAGES = ("judge_said_no", "could_not_replay", "reviewer_said_no")


@dataclass
class MatchDecision:
    run_id: str
    report: str
    page: str
    candidates: list[int]
    matched: int | None
    reason: str
    # How verification ended for this report: "verified" (kept: confirmed, or never checked),
    # "judge_said_no" (replayed, the model didn't see it), "could_not_replay", "duplicate",
    # "reviewer_said_no" (the reviewer tier dropped it before replay, run 5), "unverified"
    # (deep mode, run 9: neither replay nor a re-measurement could check it).
    stage: str = "verified"
    failure_kind: str | None = None  # for "could_not_replay": evidence.replay_failure.kind


@dataclass
class BenchmarkScores:
    provider: str
    model: str
    git_commit: str
    runs_buggy: int
    recall: float
    precision: float
    false_alarms: float
    avg_cost_usd: float
    avg_duration_s: float
    per_bug: dict[int, dict] = field(default_factory=dict)
    decisions: list[MatchDecision] = field(default_factory=list)
    judge: str = ""  # "provider/model" that matched reports to planted bugs
    # Recall over the bugs that need judgement only: the number to compare models by.
    ai_recall: float = 0.0
    holdout: "BenchmarkScores | None" = None  # the same scores on the holdout app
    rescore_commit: str | None = None  # set by `bench --rescore`
    # What verification did (run 3): see score().
    recall_before: float = 0.0
    ai_recall_before: float = 0.0
    false_alarms_before: float = 0.0
    correct_but_discarded: int = 0
    reviewer: str = ""  # "provider/model" of the reviewer tier, "" when the runs had none
    verification: dict = field(default_factory=dict)
    # Run 6, L1: API-equivalent cost (an estimate for claude-cli), None when not measured.
    avg_estimated_cost_usd: float | None = None
    estimated_cost_per_verified_bug: float | None = None
    reported_models: list[str] = field(default_factory=list)  # what the providers said ran
    benchmark_version: str = BENCHMARK_VERSION
    # Run 8, N3: 95% intervals on recall ("ai_recall", "recall"), see worker/stats.py.
    intervals: dict = field(default_factory=dict)


def load_planted(path: Path = BUGS_JSON) -> list[PlantedBug]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        PlantedBug(b["id"], b["page"], b["title"], b["description"], b["detection"])
        for b in data["bugs"]
    ]


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


def candidates_for(page_url: str, planted: list[PlantedBug]) -> list[PlantedBug]:
    """Planted bugs on the report's page; all of them if none is on that page.

    The page narrows the first question to the judge. It doesn't decide the match:
    `match_report` asks again with every planted bug when none of these fits.
    """
    on_page = [b for b in planted if b.page == path_of(page_url)]
    return on_page or planted


def judge_name(llm: LLMClient) -> str:
    """Who judged the matches, as "provider/model" (matching uses the client's cheap model)."""
    return f"{llm.provider}/{llm.cheap_model}"


def ask_judge(llm: LLMClient, report: Bug, candidates: list[PlantedBug]) -> tuple[int | None, str]:
    """Ask the cheap model which of `candidates` the report describes: (bug id or None, reason).

    An id that isn't one of the candidates counts as no match.
    """
    listing = "\n".join(f"{b.id}. [{b.page}] {b.title}: {b.description}" for b in candidates)
    prompt = (
        f"REPORT: {report.title}\nPage: {report.page_url}\n"
        f"Expected: {report.expected or '-'}\nActual: {report.actual or '-'}\n\n"
        f"KNOWN BUGS:\n{listing}"
    )
    answer = parse_json_object(llm.complete(prompt, system=MATCH_SYSTEM, cheap=True).text) or {}
    matched = as_bug_id(answer.get("match"))
    valid = matched in {b.id for b in candidates}
    return (matched if valid else None), str(answer.get("reason") or "no clear answer")


def match_report(
    llm: LLMClient, run_id: str, report: Bug, planted: list[PlantedBug]
) -> MatchDecision:
    """Match a report to a planted bug: the bugs on its page first, then every planted bug.

    The second round catches a bug seen on another page than bugs.json lists (a $NaN price
    from the product list showing up in the cart). It only runs when the first found nothing.
    """
    candidates = candidates_for(report.page_url, planted)
    matched, reason = ask_judge(llm, report, candidates)
    if matched is None and len(candidates) < len(planted):
        candidates = planted
        matched, reason = ask_judge(llm, report, candidates)
    return MatchDecision(
        run_id=run_id,
        report=report.title,
        page=path_of(report.page_url),
        candidates=sorted(b.id for b in candidates),
        matched=matched,
        reason=reason,
    )


def as_bug_id(value) -> int | None:
    """The model's "match" as an int: models write 2, 2.0 or "2" for the same answer."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def score(
    buggy: dict[str, list[MatchDecision]],
    clean_reports: dict[str, int],
    planted: list[PlantedBug],
    costs: list[float],
    durations: list[float],
    provider: str,
    model: str,
    git_commit: str,
    judge: str = "",
    clean_before: dict[str, int] | None = None,
    reviewer: str = "",
    estimated_costs: dict[str, float] | None = None,
) -> BenchmarkScores:
    """Compute the scores from match decisions (one list per buggy run).

    Only reports that survived verification (stage "verified") count for:
    recall: average over buggy runs of (distinct planted bugs found / planted bugs).
    ai_recall: the same over the bugs that need judgement only (detection "agent"): the
    deterministic checks find the others for free, whichever model runs.
    precision: matched reports / reported reports, over all buggy runs.
    false_alarms: average number of reports per clean run.

    What verification did: recall_before / ai_recall_before count every report but
    duplicates; correct_but_discarded is how many discarded reports matched a planted bug (if
    it's high, verification is too strict); false_alarms_before uses `clean_before` (reports
    per clean run before verification); `verification` holds the counts per stage.

    `estimated_costs` (run id → API-equivalent cost, buggy and clean runs): the average per run,
    and the buggy runs' total over the planted bugs they verified (each run's distinct bugs
    counted, as recall does). None when not measured or nothing was verified.
    """
    kept = {run: [d for d in ds if d.stage == "verified"] for run, ds in buggy.items()}
    seen = {run: [d for d in ds if d.stage != "duplicate"] for run, ds in buggy.items()}

    def recall_over(bugs: list[PlantedBug], runs: dict) -> list[float]:
        ids = {b.id for b in bugs}
        if not ids:
            return []
        return [len({d.matched for d in ds} & ids) / len(ids) for ds in runs.values()]

    def mean(values) -> float:
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    ai_bugs = [b for b in planted if b.detection == "agent"]
    all_decisions = [d for ds in kept.values() for d in ds]
    matched = sum(1 for d in all_decisions if d.matched is not None)
    per_bug = {
        b.id: {
            "title": b.title,
            "found_runs": sum(1 for ds in kept.values() if any(d.matched == b.id for d in ds)),
            "detection": b.detection,
        }
        for b in planted
    }
    every = [d for ds in buggy.values() for d in ds]
    discarded = [d for d in every if d.stage in DISCARD_STAGES]
    reasons = Counter(
        d.stage if d.stage != "could_not_replay" else (d.failure_kind or "unknown")
        for d in discarded
    )
    bugs_lost = sum(
        len({d.matched for d in seen[run]} - {d.matched for d in kept[run]} - {None})
        for run in buggy
    )
    verification = {
        "reported": len(every),
        "verified": len(all_decisions),
        "duplicates": sum(1 for d in every if d.stage == "duplicate"),
        # Run 9: deep-mode findings nothing could check; neither verified nor discarded.
        "unverified": sum(1 for d in every if d.stage == "unverified"),
        "discarded_at_replay": len(discarded),
        "discard_reasons": dict(sorted(reasons.items())),
        "bugs_lost": bugs_lost,
    }
    clean_before = clean_reports if clean_before is None else clean_before
    avg_estimate, per_bug_estimate = estimated_cost(estimated_costs, kept, planted)
    found_runs = [{d.matched for d in ds if d.matched is not None} for ds in kept.values()]
    intervals = {
        "ai_recall": recall_interval(found_runs, {b.id for b in ai_bugs}),
        "recall": recall_interval(found_runs, {b.id for b in planted}),
    }
    return BenchmarkScores(
        provider=provider,
        model=model,
        git_commit=git_commit,
        runs_buggy=len(buggy),
        recall=mean(recall_over(planted, kept)),
        ai_recall=mean(recall_over(ai_bugs, kept)),
        precision=matched / len(all_decisions) if all_decisions else 0.0,
        false_alarms=mean(clean_reports.values()),
        avg_cost_usd=sum(costs) / len(costs) if costs else 0.0,
        avg_duration_s=sum(durations) / len(durations) if durations else 0.0,
        per_bug=per_bug,
        decisions=every,
        judge=judge,
        reviewer=reviewer,
        recall_before=mean(recall_over(planted, seen)),
        ai_recall_before=mean(recall_over(ai_bugs, seen)),
        false_alarms_before=mean(clean_before.values()),
        correct_but_discarded=sum(1 for d in discarded if d.matched is not None),
        verification=verification,
        avg_estimated_cost_usd=avg_estimate,
        estimated_cost_per_verified_bug=per_bug_estimate,
        intervals=intervals,
    )


def intervals_from_details(details: list[dict], planted: list[PlantedBug], which: str) -> dict:
    """Recall intervals from saved results (their `details`), pooled over all of them: "shop"
    uses runs["buggy"] and decisions, "holdout" runs["holdout_buggy"] and holdout.decisions.
    Only verified reports count, as in score(). For results saved before run 8 and for
    benchmarks split into parts (run 8, N3)."""
    found: dict[str, set[int]] = {}
    for d in details:
        runs = (d.get("runs") or {}).get("buggy" if which == "shop" else "holdout_buggy") or []
        part = d if which == "shop" else (d.get("holdout") or {})
        for run_id in runs:
            found.setdefault(run_id, set())
        for decision in part.get("decisions") or []:
            if decision.get("stage", "verified") == "verified" and decision.get("matched"):
                if decision["run_id"] in found:
                    found[decision["run_id"]].add(decision["matched"])
    runs = list(found.values())
    return {
        "ai_recall": recall_interval(runs, {b.id for b in planted if b.detection == "agent"}),
        "recall": recall_interval(runs, {b.id for b in planted}),
    }


def estimated_cost(
    costs: dict[str, float] | None, kept: dict[str, list], planted: list[PlantedBug]
) -> tuple[float | None, float | None]:
    """(average API-equivalent cost per run, buggy runs' cost per verified planted bug)."""
    if not costs:
        return None, None
    ids = {b.id for b in planted}
    verified = sum(len({d.matched for d in ds} & ids) for ds in kept.values())
    buggy_cost = sum(costs.get(run, 0.0) for run in kept)
    return sum(costs.values()) / len(costs), (buggy_cost / verified if verified else None)


def check_pinned_models(clients: list) -> None:
    """A claude-cli benchmark must name its models by full ID: an alias ("sonnet") moves to a
    newer model without notice, and the result would no longer say which model ran (run 6)."""
    from worker.llm.claude_cli import is_pinned_model_id

    for client in clients:
        if client is None or client.provider != "claude-cli":
            continue
        for model in (client.agent_model, client.cheap_model):
            if not is_pinned_model_id(model):
                raise ValueError(
                    f"claude-cli model {model!r} is an alias: set CLAUDE_CLI_MODEL / "
                    "CLAUDE_CLI_CHEAP_MODEL (or REVIEWER_MODEL) to a full ID like claude-sonnet-5-5"
                )


def stop_reason(session: Session, run_ids: list[str], cap_usd: float) -> str | None:
    """Why a benchmark must stop now, or None: a claude-cli usage limit (or a call paid from
    credits) in this process, or the runs' API-equivalent cost reaching BENCH_MAX_COST_USD."""
    from worker.llm.claude_cli import limit_reached

    if why := limit_reached():
        return f"claude-cli stopped: {why}"
    runs = session.query(Run).filter(Run.id.in_(run_ids)).all()
    if paused := [r for r in runs if r.status == "paused"]:
        return f"a deep run paused on a usage limit ({paused[0].paused_reason})"
    spent = sum(r.estimated_cost_usd for r in session.query(Run).filter(Run.id.in_(run_ids)))
    if cap_usd > 0 and spent >= cap_usd:
        return f"estimated cost cap reached (${spent:.2f} of ${cap_usd:.2f}, API-equivalent)"
    return None


def stop_queued(session: Session, run_ids: list[str], reason: str) -> int:
    """Stop the benchmark's runs that haven't started; returns how many."""
    from worker.db.models import RunStatus
    from worker.queue import transition

    queued = session.query(Run).filter(Run.id.in_(run_ids), Run.status == RunStatus.QUEUED).all()
    for run in queued:
        transition(run, RunStatus.STOPPED, error=f"not started: benchmark stopped ({reason})")
    session.commit()
    return len(queued)


def reported_models(session: Session, run_ids: list[str]) -> list[str]:
    """Every model the providers reported for these runs' calls (steps.model), sorted."""
    from worker.db.models import Step

    rows = (
        session.query(Step.model)
        .filter(Step.run_id.in_(run_ids), Step.model.is_not(None))
        .distinct()
        .all()
    )
    return sorted(model for (model,) in rows)


def stage_of(bug) -> tuple[str, str | None]:
    """How verification ended for a stored bug: (stage, failure kind). See MatchDecision."""
    if bug.duplicate_of_id is not None:
        return "duplicate", None
    if bug.status == "unverified":  # run 9: nothing could check it; never counted as found
        return "unverified", None
    if bug.status != "dismissed":
        return "verified", None
    reason = bug.dismiss_reason or ""
    if reason.startswith("reviewer:"):
        return "reviewer_said_no", None
    if reason.startswith("could not replay"):
        kind = ((bug.evidence or {}).get("replay_failure") or {}).get("kind", "unknown")
        return "could_not_replay", kind
    return "judge_said_no", None


def reviewer_of(runs: list) -> str:
    """ "provider/model" of the reviewer tier the runs used ("" for none): part of the settings
    a benchmark result is recorded with, like the judge."""
    for run in runs:
        if run.reviewer_model:
            return f"{run.reviewer_provider}/{run.reviewer_model}"
    return ""


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def benchmark_workspace(session: Session) -> Workspace:
    workspace = session.query(Workspace).filter_by(slug=BENCHMARK_SLUG).one_or_none()
    if workspace is None:
        workspace = Workspace(name="Benchmark", slug=BENCHMARK_SLUG)
        session.add(workspace)
        session.commit()
    return workspace


def queue_runs(
    session: Session, workspace_id, urls: list[str], mode: str, engine: str = "loop"
) -> list[str]:
    """`engine`: "loop" (the current agent) or "deep" (run 9, always interactive)."""
    ids = []
    for url in urls:
        mode = "interactive" if engine == "deep" else mode
        run = Run(workspace_id=workspace_id, target_url=url, mode=mode, focus=None, engine=engine)
        session.add(run)
        session.commit()
        ids.append(str(run.id))
    return ids


def wait_for(sessions: sessionmaker[Session], run_ids: list[str], process) -> list[Run]:
    """Process queued runs in this process until all of ours are final (another worker may
    take some; then we wait for it)."""
    while True:
        with sessions() as session:
            runs = [session.get(Run, run_id) for run_id in run_ids]
            if all(run.status in FINAL or run.status == "paused" for run in runs):
                return runs
        if not process():
            time.sleep(1)


def report_bugs(session: Session, run_id: str) -> list[Bug]:
    """What the run reports to the user: every bug that wasn't dismissed or suppressed."""
    return (
        session.query(Bug)
        .filter(
            Bug.run_id == run_id,
            Bug.status.not_in(("dismissed", "unverified")),
            Bug.suppressed.is_(False),
        )
        .order_by(Bug.created_at)
        .all()
    )


def print_scores(scores: BenchmarkScores) -> None:
    print()
    print(
        f"Benchmark {scores.benchmark_version} · {scores.provider} · {scores.model}"
        f" · commit {scores.git_commit}"
    )
    if scores.rescore_commit:
        print(f"  rescored at    {scores.rescore_commit}")
    print(f"  judge          {scores.judge or 'not recorded'}")
    _print_set("demo shop", scores)
    if scores.holdout:
        _print_set("holdout app (apps/demo2, never tuned against)", scores.holdout)
    print(f"  avg cost       ${scores.avg_cost_usd:.3f}  (charged)")
    if scores.reported_models:
        print(f"  models (as reported by the provider) {', '.join(scores.reported_models)}")
    print(f"  avg duration   {scores.avg_duration_s:.0f} s")


def _print_estimates(scores: BenchmarkScores) -> None:
    if scores.avg_estimated_cost_usd is None:
        return
    per_bug = scores.estimated_cost_per_verified_bug
    print(f"  est. API cost / run           ${scores.avg_estimated_cost_usd:.3f}")
    print(
        "  est. API cost / verified bug  "
        + (f"${per_bug:.3f}" if per_bug is not None else "- (no verified planted bug)")
    )
    print("  (estimates: list-price cost of the calls' token counts, not a charge)")


def _print_set(name: str, scores: BenchmarkScores) -> None:
    print()
    print(f"  {name}: {scores.runs_buggy} buggy runs")
    print(f"  AI-only recall {scores.ai_recall:.0%}  (bugs that need judgement, found per run)")
    print(f"  recall         {scores.recall:.0%}  (all planted bugs, incl. the free checks)")
    if scores.intervals:
        print("  95% interval   AI-only " + fmt(scores.intervals["ai_recall"]))
        print("                 all     " + fmt(scores.intervals["recall"]))
    print(f"  precision      {scores.precision:.0%}  (reports that matched a planted bug)")
    print(f"  false alarms   {scores.false_alarms:.1f}  (reports per run on the clean build)")
    funnel = scores.verification
    if funnel:
        reasons = ", ".join(f"{k} {n}" for k, n in funnel["discard_reasons"].items()) or "none"
        print(
            f"  verification   reported {funnel['reported']} → verified {funnel['verified']}"
            f" (duplicates {funnel['duplicates']},"
            f" discarded at replay {funnel['discarded_at_replay']}"
            # Deep mode only (run 9): findings nothing could check.
            + (f", unverified {funnel['unverified']})" if funnel.get("unverified") else ")")
        )
        print(f"  discarded because       {reasons}")
        print(
            f"  correct but discarded  {scores.correct_but_discarded}"
            f"  (discarded reports that match a planted bug; {funnel['bugs_lost']} bug(s) lost)"
        )
        print(
            f"  recall before verification {scores.recall_before:.0%},"
            f" AI-only {scores.ai_recall_before:.0%}"
        )
        print(f"  false alarms before verification {scores.false_alarms_before:.1f}")
    _print_estimates(scores)
    print("  per bug (found in N of the buggy runs):")
    for bug_id, info in scores.per_bug.items():
        mark = "✓" if info["found_runs"] else "·"
        kind = "AI " if info.get("detection") == "agent" else "det"
        line = f"   {mark} {kind} {bug_id:>2}. {info['title']}"
        print(f"{line}  [{info['found_runs']}/{scores.runs_buggy}]")


def verification_details(scores: BenchmarkScores) -> dict:
    """What verification did, as saved in the result's details (no columns: nothing sorts or
    filters on these; the leaderboard reads them from the row it already loads)."""
    return {
        **scores.verification,
        "recall_before": scores.recall_before,
        "ai_recall_before": scores.ai_recall_before,
        "false_alarms_before": scores.false_alarms_before,
        "correct_but_discarded": scores.correct_but_discarded,
    }


def all_reports(session: Session, run_id: str) -> list[Bug]:
    """Every bug the run produced, including the ones verification dismissed."""
    return session.query(Bug).filter(Bug.run_id == run_id).order_by(Bug.created_at).all()


def staged_match(llm: LLMClient, run_id: str, report: Bug, planted: list[PlantedBug]):
    """match_report plus how verification ended for the report. Duplicates aren't matched:
    the report they duplicate already is, and they would only cost judge calls."""
    stage, kind = stage_of(report)
    if stage == "duplicate":
        decision = MatchDecision(run_id, report.title, path_of(report.page_url), [], None, "")
    else:
        decision = match_report(llm, run_id, report, planted)
    decision.stage, decision.failure_kind = stage, kind
    return decision


def save_scores(
    session: Session, scores: BenchmarkScores, run_ids: dict, extra: dict | None = None
) -> BenchmarkResult:
    """Save a result. `extra` goes into details (an incomplete benchmark: "invalid", which
    keeps it off the leaderboard, and "incomplete")."""
    data = asdict(scores)
    holdout = scores.holdout
    details = {
        "per_bug": {str(k): v for k, v in data["per_bug"].items()},
        "decisions": data["decisions"],
        "runs": run_ids,
        "judge": scores.judge,
        "reviewer": scores.reviewer or None,
        "verification": verification_details(scores),
        "reported_models": scores.reported_models,
        "intervals": scores.intervals,
        **(extra or {}),
    }
    if holdout:
        details["holdout"] = {
            "per_bug": {str(k): v for k, v in asdict(holdout)["per_bug"].items()},
            "decisions": asdict(holdout)["decisions"],
            "verification": verification_details(holdout),
            "avg_estimated_cost_usd": holdout.avg_estimated_cost_usd,
            "estimated_cost_per_verified_bug": holdout.estimated_cost_per_verified_bug,
            "intervals": holdout.intervals,
        }
    result = BenchmarkResult(
        provider=scores.provider,
        model=scores.model,
        git_commit=scores.git_commit,
        runs_buggy=scores.runs_buggy,
        recall=scores.recall,
        precision=scores.precision,
        false_alarms=scores.false_alarms,
        avg_cost_usd=scores.avg_cost_usd,
        avg_duration_s=scores.avg_duration_s,
        ai_recall=scores.ai_recall,
        holdout_runs_buggy=holdout.runs_buggy if holdout else None,
        holdout_recall=holdout.recall if holdout else None,
        holdout_ai_recall=holdout.ai_recall if holdout else None,
        holdout_precision=holdout.precision if holdout else None,
        holdout_false_alarms=holdout.false_alarms if holdout else None,
        judge=scores.judge or None,
        rescore_commit=scores.rescore_commit,
        avg_estimated_cost_usd=scores.avg_estimated_cost_usd,
        estimated_cost_per_verified_bug=scores.estimated_cost_per_verified_bug,
        benchmark_version=scores.benchmark_version,
        details=details,
    )
    session.add(result)
    session.commit()
    return result
