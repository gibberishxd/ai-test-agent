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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.orm import Session, sessionmaker

from worker.config import REPO_ROOT
from worker.db.models import BenchmarkResult, Bug, Run, Workspace
from worker.llm import LLMClient
from worker.queue import FINAL
from worker.verify import parse_json_object

BUGS_JSON = REPO_ROOT / "apps" / "demo" / "bugs.json"

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


@dataclass
class MatchDecision:
    run_id: str
    report: str
    page: str
    candidates: list[int]
    matched: int | None
    reason: str


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


def load_planted(path: Path = BUGS_JSON) -> list[PlantedBug]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [PlantedBug(b["id"], b["page"], b["title"], b["description"]) for b in data["bugs"]]


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
) -> BenchmarkScores:
    """Compute the scores from match decisions (one list per buggy run).

    recall: average over buggy runs of (distinct planted bugs found / planted bugs).
    precision: matched reports / all reports, over all buggy runs (duplicates of a real bug
    count as matched, not as false alarms).
    false_alarms: average number of reports per clean run.
    """
    total = len(planted)
    recalls = [
        len({d.matched for d in ds if d.matched is not None}) / total for ds in buggy.values()
    ]
    all_decisions = [d for ds in buggy.values() for d in ds]
    matched = sum(1 for d in all_decisions if d.matched is not None)
    per_bug = {
        b.id: {
            "title": b.title,
            "found_runs": sum(1 for ds in buggy.values() if any(d.matched == b.id for d in ds)),
        }
        for b in planted
    }
    return BenchmarkScores(
        provider=provider,
        model=model,
        git_commit=git_commit,
        runs_buggy=len(buggy),
        recall=sum(recalls) / len(recalls) if recalls else 0.0,
        precision=matched / len(all_decisions) if all_decisions else 0.0,
        false_alarms=sum(clean_reports.values()) / len(clean_reports) if clean_reports else 0.0,
        avg_cost_usd=sum(costs) / len(costs) if costs else 0.0,
        avg_duration_s=sum(durations) / len(durations) if durations else 0.0,
        per_bug=per_bug,
        decisions=all_decisions,
        judge=judge,
    )


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def benchmark_workspace(session: Session) -> Workspace:
    workspace = session.query(Workspace).filter_by(slug="benchmark").one_or_none()
    if workspace is None:
        workspace = Workspace(name="Benchmark", slug="benchmark")
        session.add(workspace)
        session.commit()
    return workspace


def queue_runs(session: Session, workspace_id, urls: list[str], mode: str) -> list[str]:
    ids = []
    for url in urls:
        run = Run(workspace_id=workspace_id, target_url=url, mode=mode, focus=None)
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
            if all(run.status in FINAL for run in runs):
                return runs
        if not process():
            time.sleep(1)


def report_bugs(session: Session, run_id: str) -> list[Bug]:
    """What the run reports to the user: every bug that wasn't dismissed."""
    return (
        session.query(Bug)
        .filter(Bug.run_id == run_id, Bug.status != "dismissed")
        .order_by(Bug.created_at)
        .all()
    )


def print_scores(scores: BenchmarkScores) -> None:
    print()
    print(f"Benchmark · {scores.provider} · {scores.model} · commit {scores.git_commit}")
    print(f"  judge          {scores.judge or 'not recorded'}")
    print(f"  buggy runs     {scores.runs_buggy}")
    print(f"  recall         {scores.recall:.0%}  (planted bugs found per run, averaged)")
    print(f"  precision      {scores.precision:.0%}  (reports that matched a planted bug)")
    print(f"  false alarms   {scores.false_alarms:.1f}  (reports per run on the clean shop)")
    print(f"  avg cost       ${scores.avg_cost_usd:.3f}")
    print(f"  avg duration   {scores.avg_duration_s:.0f} s")
    print()
    print("  per bug (found in N of the buggy runs):")
    for bug_id, info in scores.per_bug.items():
        mark = "✓" if info["found_runs"] else "·"
        print(f"   {mark} {bug_id:>2}. {info['title']}  [{info['found_runs']}/{scores.runs_buggy}]")


def save_scores(session: Session, scores: BenchmarkScores, run_ids: dict) -> BenchmarkResult:
    data = asdict(scores)
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
        details={
            "per_bug": {str(k): v for k, v in data["per_bug"].items()},
            "decisions": data["decisions"],
            "runs": run_ids,
            "judge": scores.judge,
        },
    )
    session.add(result)
    session.commit()
    return result
