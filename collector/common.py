"""Shared helpers for Grid Pulse collectors.

Stdlib only — this runs on GitHub Actions cron without a `pip install` step.
Design rules (from the jam-genome playbook): never crash on a single-source
failure, log gaps explicitly, and be idempotent per slot so the cron can be
safely over-scheduled.
"""
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from collector.config import USER_AGENT

# India has a single timezone and no DST — one genuine mercy in this domain.
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc


def now_ist() -> datetime:
    return datetime.now(IST)


def slot_floor(dt: datetime, minutes: int) -> datetime:
    """Floor a datetime to its `minutes`-slot (e.g. 15:07:42 -> 15:00:00 at 15 min)."""
    discard = (dt.minute % minutes) * 60 + dt.second
    return (dt - timedelta(seconds=discard)).replace(microsecond=0)


def slot_key(dt: datetime, minutes: int) -> str:
    """Stable string id for a slot, e.g. '2026-07-12T15:00'."""
    return slot_floor(dt, minutes).strftime("%Y-%m-%dT%H:%M")


def http_get(url: str, retries: int = 4, backoff: float = 2.0,
             timeout: int = 30, headers: dict | None = None) -> bytes:
    """HTTP GET with exponential backoff. Returns the body bytes; raises on final failure."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(backoff ** attempt)  # 1s, 2s, 4s, ...
    raise last_err  # type: ignore[misc]


def append_jsonl(path, record: dict) -> None:
    """Append one JSON record as a line. Creates parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path) -> list[dict]:
    """Read a JSONL file into a list of dicts. Missing file -> []. Skips bad lines."""
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(h)
    return logger
