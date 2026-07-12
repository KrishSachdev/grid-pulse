"""One-off backfill: Grid-India daily PSP reports -> per-state daily history.

Downloads the NLDC daily PSP XLS files (complete from FY 2023-24 onward; earlier
years are PDF-only) and extracts the state row from the `MOP_E` sheet:

    Region | State | Max Demand Met (MW) | Shortage@Peak (MW) | Energy Met (MU)
           | Drawal Schedule (MU) | OD/UD (MU) | Max OD/UD (MW) | Energy Shortage (MU)

Output: data/history/psp/<state>.jsonl — one record per day, sorted, deduped.
Raw XLS files are cached in cache/psp/ (gitignored) so the job is resumable and
re-runs never re-download. Run it any time to top up history to yesterday.

This is a LOCAL job, not part of the Actions cron. Needs `xlrd` (pip install xlrd).

Usage (from repo root):
    python -m collector.backfill_psp                 # default: 2023-04-01 -> today
    python -m collector.backfill_psp --since 2024-01-01
"""
import argparse
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import common
from collector.config import DATA_HISTORY, REPO_ROOT, USER_AGENT

log = common.get_logger("backfill_psp")

API_LIST = "https://webapi.grid-india.in/api/v1/file"
CDN = "https://webcdn.grid-india.in/"
CACHE_DIR = REPO_ROOT / "cache" / "psp"
OUT_DIR = DATA_HISTORY / "psp"

# grid-india.in serves an incomplete TLS chain (verified 2026-07-12), so system
# cert stores can't validate it. Public data, read-only — we proceed unverified,
# same as `curl -k`.
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

STATES = {"maharashtra": "Maharashtra"}  # output-slug -> MOP_E row label

# Sanity ranges guard against silent column-layout drift: if a "demand" cell
# doesn't look like MW we refuse the parse rather than record garbage.
DEMAND_MW_RANGE = (1_000, 60_000)   # MH daily peak is ~15-30 GW
ENERGY_MU_RANGE = (100, 2_000)      # MH daily energy is ~400-700 MU


def http(url: str, retries: int = 4, timeout: int = 60, post_json: dict | None = None) -> bytes:
    """GET/POST with backoff, custom UA, and the unverified-TLS context."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            headers = {"User-Agent": USER_AGENT, "Origin": "https://grid-india.in"}
            data = None
            if post_json is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(post_json).encode()
            req = urllib.request.Request(url, headers=headers, data=data)
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                return r.read()
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise last  # type: ignore[misc]


def legacy_url(d: date) -> str:
    """Deterministic URL on the legacy portal (covers ~2013 -> May 2025)."""
    fy = d.year if d.month >= 4 else d.year - 1
    folder = f"{fy}-{fy + 1}/{d.strftime('%B %Y')}"
    name = d.strftime("%d.%m.%y") + "_NLDC_PSP.xls"
    return ("https://report.grid-india.in/ReportData/Daily Report/PSP Report/"
            f"{folder}/{name}").replace(" ", "%20")


def list_xls_files() -> list[dict]:
    """All PSP XLS files from the webapi, as [{date, url, name}] sorted by date."""
    raw = json.loads(http(API_LIST, post_json={"_source": "GRDW", "_type": "DAILY_PSP_REPORT"}))
    out = []
    for r in raw.get("retData", []):
        title, path = r.get("Title_", ""), r.get("FilePath", "")
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})_NLDC_PSP", title)
        if not m or not re.search(r"\.xlsx?$", path, re.I):
            continue
        d = date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))
        out.append({"date": d, "url": CDN + path, "name": Path(path).name})
    # webapi occasionally lists a day twice; keep the last-listed entry per date
    dedup: dict[date, dict] = {}
    for f in out:
        dedup[f["date"]] = f
    return sorted(dedup.values(), key=lambda f: f["date"])


def _sheet_rows(xls_path: Path):
    """Yield MOP_E rows as lists of cell values; handles both .xls and .xlsx."""
    if xls_path.suffix.lower() == ".xlsx":
        import openpyxl  # a handful of days were uploaded as xlsx
        ws = openpyxl.load_workbook(str(xls_path), read_only=True, data_only=True)["MOP_E"]
        for row in ws.iter_rows(values_only=True):
            yield list(row)
    else:
        import xlrd  # local import: only this one-off job needs it
        sh = xlrd.open_workbook(str(xls_path)).sheet_by_name("MOP_E")
        for r in range(sh.nrows):
            yield [sh.cell_value(r, c) for c in range(sh.ncols)]


def parse_mop_e(xls_path: Path, row_label: str) -> dict | None:
    """Extract one state's row from the MOP_E sheet. None if not found/implausible."""
    for cells in _sheet_rows(xls_path):
        if len(cells) < 9 or str(cells[1] or "").strip().lower() != row_label.lower():
            continue
        def num(c):
            v = cells[c]
            return float(v) if isinstance(v, (int, float)) else None
        demand, energy = num(2), num(4)
        if demand is None or not (DEMAND_MW_RANGE[0] <= demand <= DEMAND_MW_RANGE[1]):
            return None  # layout drift or nonsense value — caller records a gap
        if energy is not None and not (ENERGY_MU_RANGE[0] <= energy <= ENERGY_MU_RANGE[1]):
            energy = None
        return {
            "peak_demand_met_mw": int(demand),
            "peak_shortage_mw": num(3),
            "energy_met_mu": energy,
            "drawal_schedule_mu": num(5),
            "od_ud_mu": num(6),
            "energy_shortage_mu": num(8),
        }
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2023-04-01", help="first date to backfill (YYYY-MM-DD)")
    ap.add_argument("--until", default=None, help="last date (default: today)")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between downloads")
    args = ap.parse_args()
    since = datetime.strptime(args.since, "%Y-%m-%d").date()
    until = datetime.strptime(args.until, "%Y-%m-%d").date() if args.until else date.today()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("listing PSP files from webapi ...")
    files = [f for f in list_xls_files() if since <= f["date"] <= until]
    log.info("%d XLS files in range %s -> %s", len(files), since, until)

    # Load what we already have so re-runs only fetch/parse the delta.
    existing: dict[str, dict[str, dict]] = {}
    for slug in STATES:
        existing[slug] = {rec["date"]: rec for rec in common.read_jsonl(OUT_DIR / f"{slug}.jsonl")}

    downloaded = parsed = gaps = 0
    for f in files:
        iso = f["date"].isoformat()
        if all(iso in existing[slug] and existing[slug][iso].get("ok") for slug in STATES):
            continue  # already parsed for every state

        xls = CACHE_DIR / f["name"]
        if not xls.exists():
            try:
                xls.write_bytes(http(f["url"]))
                downloaded += 1
                time.sleep(args.delay)
            except Exception as e:
                # A few days 404 on the new CDN but exist on the legacy portal
                # (report.grid-india.in mirrors PSP up to ~May 2025).
                try:
                    xls.write_bytes(http(legacy_url(f["date"])))
                    downloaded += 1
                    time.sleep(args.delay)
                    log.info("recovered %s from legacy portal", f["name"])
                except Exception:
                    log.warning("download failed %s: %s", f["name"], e)
                    gaps += 1
                    continue

        for slug, label in STATES.items():
            try:
                vals = parse_mop_e(xls, label)
            except Exception as e:
                vals = None
                log.warning("parse error %s (%s): %s", f["name"], slug, e)
            if vals is None:
                existing[slug][iso] = {"date": iso, "ok": False, "source_file": f["name"]}
                gaps += 1
            else:
                existing[slug][iso] = {"date": iso, "ok": True, "source_file": f["name"],
                                       "source": "grid-india-psp", **vals}
                parsed += 1

    # Rewrite outputs sorted by date (idempotent, dedup by construction).
    for slug in STATES:
        out = OUT_DIR / f"{slug}.jsonl"
        with open(out, "w", encoding="utf-8") as fh:
            for iso in sorted(existing[slug]):
                fh.write(json.dumps(existing[slug][iso], ensure_ascii=False) + "\n")
        n_ok = sum(1 for r in existing[slug].values() if r.get("ok"))
        log.info("%s: %d days ok (of %d) -> %s", slug, n_ok, len(existing[slug]),
                 out.relative_to(REPO_ROOT))

    log.info("done: %d downloaded, %d parsed, %d gaps", downloaded, parsed, gaps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
