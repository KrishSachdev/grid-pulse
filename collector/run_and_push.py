"""Collect + commit + push, from a machine inside India.

WHY THIS EXISTS
---------------
GitHub-hosted runners cannot reach India's grid portals. Measured 2026-07-16 →
2026-08-10: 343 scheduled attempts, both vidyutpravah AND meritindia, **zero**
successes (`URLError` every time) — while the same URLs return HTTP 200 from a
machine in India at the same moments. Weather (Open-Meteo) is unaffected.

So the hourly demand collector has to run on hardware in India (NAS / PC), which
is the "Task Scheduler fallback" the plan budgeted for. This script is the entry
point for that: it runs the collectors, commits whatever is new, and pushes —
rebasing if the Actions bot (weather) pushed meanwhile.

SETUP (Synology NAS — preferred, it's always on)
    Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script
    Schedule: every 15 min.  Command:
        cd /volume1/<path>/grid-pulse && /usr/local/bin/python3 -m collector.run_and_push
    Git auth: store a PAT once via
        git remote set-url origin https://<PAT>@github.com/KrishSachdev/grid-pulse.git

SETUP (Windows PC — fallback, only collects while the PC is on)
    Task Scheduler → Create Task → Trigger: repeat every 15 min →
    Action: py -3 -m collector.run_and_push   (Start in: the repo folder)

Safe to run as often as you like: the collectors' slot guard keeps one reading
per hour, and a run with nothing new simply exits without committing.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import common
from collector.config import REPO_ROOT

log = common.get_logger("run_and_push")


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=check,
                          capture_output=True, text=True)


def main() -> int:
    # 1. Collect. Each collector is already crash-proof and logs its own gaps.
    for mod in ("collector.fetch_demand", "collector.fetch_weather"):
        r = subprocess.run([sys.executable, "-m", mod], cwd=REPO_ROOT,
                           capture_output=True, text=True)
        if r.stderr.strip():
            log.info("%s: %s", mod.split(".")[-1], r.stderr.strip().splitlines()[-1])

    # 2. Anything new? (data/ only — never sweep up unrelated working-tree edits.)
    git("add", "data")
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        log.info("no new data to push")
        return 0

    stamp = common.now_ist().strftime("%Y-%m-%dT%H:%M IST")
    git("commit", "-m", f"data: collect {stamp} (local runner)")

    # 3. Push, rebasing over the Actions bot if it pushed while we were working.
    for attempt in range(3):
        if not git("pull", "--rebase", "--autostash", check=False).returncode:
            if not git("push", check=False).returncode:
                log.info("pushed: %s", stamp)
                return 0
        log.warning("push attempt %d failed; retrying", attempt + 1)
    log.error("could not push after 3 attempts — will retry next run")
    return 0  # never fail the scheduled task; the commit is safe locally


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("unexpected fatal error in run_and_push")
        sys.exit(0)
