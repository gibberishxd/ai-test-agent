"""Fetch, start and stop the real-world benchmark's apps (run 8, N4).

    cd apps/worker && uv run python ../realworld/realworld.py setup IT-1   # clone + install
    cd apps/worker && uv run python ../realworld/realworld.py start IT-1   # dev server on its port
    cd apps/worker && uv run python ../realworld/realworld.py check IT-1   # reproduces?
    cd apps/worker && uv run python ../realworld/realworld.py stop IT-1    # by its saved PID

Each bug runs its app at the commit just before the fix (the fix's first parent), in its own git
worktree under ~/ai-test-agent-realworld (REALWORLD_DIR): the apps' source never enters this repo.
Clones are blobless (`--filter=blob:none`): git fetches only the files a checkout needs. The
started server's PID is saved next to the worktree and `stop` kills exactly that process group.
No Anthropic credential is passed to the apps.
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUGS = HERE / "bugs.json"
ROOT = Path(os.environ.get("REALWORLD_DIR", Path.home() / "ai-test-agent-realworld"))
CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def load() -> dict:
    return json.loads(BUGS.read_text(encoding="utf-8"))


def bug_and_app(bug_id: str) -> tuple[dict, dict]:
    data = load()
    bug = next(b for b in data["bugs"] if b["id"] == bug_id)
    return bug, data["apps"][bug["app"]]


def env_for(app: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in CREDENTIALS}
    env.update(app.get("env", {}))
    if app.get("node_bin"):  # an app whose config needs an older Node (react-admin: Node 20)
        env["PATH"] = f"{app['node_bin']}:{env.get('PATH', '')}"
    env["BROWSER"] = "none"  # never open a browser window
    return env


def git(*args: str, cwd: Path) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def source_clone(bug: dict, app: dict) -> Path:
    src = ROOT / f"{bug['app']}-src"
    if not src.exists():
        ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "-q", "--filter=blob:none", "--no-checkout", app["repo"], str(src)],
            check=True,
        )
    return src


def worktree(bug: dict) -> Path:
    return ROOT / f"{bug['app']}-{bug['id']}"


def setup(bug_id: str) -> None:
    bug, app = bug_and_app(bug_id)
    src = source_clone(bug, app)
    fix = bug["fix_commit"]
    subprocess.run(["git", "fetch", "-q", "origin", fix], cwd=src, check=False)
    full = git("rev-parse", fix, cwd=src)
    parent = git("rev-parse", f"{full}^", cwd=src)
    tree = worktree(bug)
    if not tree.exists():
        git("worktree", "add", "-q", "--detach", str(tree), parent, cwd=src)
    head = git("rev-parse", "HEAD", cwd=tree)
    assert head == parent, f"{tree} is at {head}, expected {parent}"
    print(f"{bug_id}: {app['repo']} at {parent[:12]} (parent of fix {full[:12]}) in {tree}")
    started = time.monotonic()
    subprocess.run(bug.get("install") or app["install"], cwd=tree, env=env_for(app), check=True)
    for step in bug.get("prepare", []):  # e.g. build packages an older checkout imports built
        subprocess.run(step["command"], cwd=tree / step["dir"], env=env_for(app), check=True)
    print(f"{bug_id}: installed in {time.monotonic() - started:.0f} s")


def url_of(bug: dict) -> str:
    return f"http://localhost:{bug['port']}"


def pid_file(bug: dict) -> Path:
    return ROOT / f"{bug['app']}-{bug['id']}.pid"


def start(bug_id: str, wait_s: int = 180) -> None:
    bug, app = bug_and_app(bug_id)
    tree = worktree(bug)
    start_command = bug.get("start") or app["start"]  # a bug may need an older tool version
    command = [part.replace("{port}", str(bug["port"])) for part in start_command]
    log = (ROOT / f"{bug['app']}-{bug['id']}.log").open("w")
    process = subprocess.Popen(
        command,
        cwd=tree / app["start_dir"],
        env=env_for(app),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # its own process group, so stop() ends vite's children too
    )
    pid_file(bug).write_text(str(process.pid))
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        request = urllib.request.Request(url_of(bug), headers={"Accept": "text/html"})
        try:
            with urllib.request.urlopen(request, timeout=5):
                print(f"{bug_id}: up at {url_of(bug)} (pid {process.pid})")
                return
        except urllib.error.HTTPError:  # any HTTP answer: the server is up
            print(f"{bug_id}: up at {url_of(bug)} (pid {process.pid})")
            return
        except OSError:
            time.sleep(2)
    raise SystemExit(f"{bug_id}: not up after {wait_s} s (log: {log.name})")


def stop(bug_id: str) -> None:
    bug, _ = bug_and_app(bug_id)
    path = pid_file(bug)
    if not path.exists():
        print(f"{bug_id}: no saved PID")
        return
    pid = int(path.read_text())
    try:
        os.killpg(pid, signal.SIGTERM)  # the group this script started, by its leader's PID
        print(f"{bug_id}: stopped process group {pid}")
    except (ProcessLookupError, PermissionError):  # gone, or only a zombie left to be reaped
        print(f"{bug_id}: process {pid} had already ended")
    path.unlink()


def check(bug_id: str) -> None:
    from checks import CHECKS  # the scripted reproduction checks (Playwright)
    from playwright.sync_api import sync_playwright

    bug, _ = bug_and_app(bug_id)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            reproduced, evidence = CHECKS[bug_id](page, url_of(bug))
        finally:
            browser.close()
    print(f"{bug_id}: {'REPRODUCES' if reproduced else 'does NOT reproduce'}: {evidence}")
    raise SystemExit(0 if reproduced else 1)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    command, bug_id = sys.argv[1], sys.argv[2]
    {"setup": setup, "start": start, "stop": stop, "check": check}[command](bug_id)
