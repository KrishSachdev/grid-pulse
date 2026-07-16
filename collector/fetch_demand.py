"""Fetch live per-state electricity demand from vidyutpravah.in.

Collector-first: vidyutpravah server-renders each state's live "Demand Met" (MW),
refreshing every ~1-5 min. We poll on an hourly slot grid and store one reading per
slot per state, building our own per-state hourly demand dataset from now on — there
is no historical hourly backfill, so accumulation starts today.

Output: data/raw/demand/YYYY-MM-DD.jsonl  (one line per state per slot; IST day).

Guarantees:
  * Never crashes on a single-source failure — writes a gap record and continues.
  * Idempotent per slot — safe to over-schedule on GitHub Actions cron (a slot that
    already has a good reading is skipped; a slot that only failed before is retried).
  * Exit code: 0 for success or transient network gaps; 1 only on a *schema break*
    (the demand span vanished / unparseable) so the workflow surfaces it loudly — a
    silent parse failure is the one thing that would quietly rot the scoreboard.

Run:  python -m collector.fetch_demand      (from the repo root)
"""
import re
import sys
from pathlib import Path

# Allow running as `python collector/fetch_demand.py` too, not only `-m`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import common
from collector.config import (
    DEMAND_DIR,
    DEMAND_SLOT_MINUTES,
    MERIT_URL,
    REPO_ROOT,
    STATES,
    VIDYUTPRAVAH_URL,
)

log = common.get_logger("fetch_demand")

# vidyutpravah value spans, verified 2026-07-12. Markup looks like:
#   <span class="value_DemandMET_en value_StateDetails_en"><span ...> 20,679&nbsp;MW</span></span>
# The label span (value_DemandMET_Top_en) is a *different* class and is not matched.
FIELDS = {
    "demand_met_mw":      "value_DemandMET_en",       # current live demand met (MW) — the target
    "prev_demand_met_mw": "value_PrevDemandMET_en",   # same time yesterday (a free persistence ref)
    "exchange_price_rs":  "value_PrevExchangePrice_en",
}

# vidyutpravah's WAF resets connections from GitHub-runner IPs when hit with a
# non-browser User-Agent (observed 2026-07-13: every Actions fetch failed with
# ECONNRESET while local fetches succeeded). Present as a regular browser.
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://vidyutpravah.in/",
}


def extract_number(html: str, css_class: str):
    """Return the first number rendered inside a span carrying exactly `css_class`.

    Anchored on the class token so it won't grab a neighbouring field's value. The
    class may be followed by others (`class="value_DemandMET_en value_StateDetails_en"`).
    """
    m = re.search(
        r'class="[^"]*\b' + re.escape(css_class) + r'\b[^"]*"[^>]*>'  # the opening span
        r'(?:\s*<span[^>]*>)?'                                         # optional inner span
        r'\s*([\d,]+(?:\.\d+)?)',                                      # the number
        html,
    )
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def fetch_vidyutpravah(slug: str) -> dict:
    """Parse vidyutpravah's state page. Returns fields dict; raises on fetch failure,
    returns {} on parse failure (schema break)."""
    url = VIDYUTPRAVAH_URL.format(slug=slug)
    html = common.http_get(url, headers=BROWSER_HEADERS).decode("utf-8", errors="replace")
    demand = extract_number(html, FIELDS["demand_met_mw"])
    if demand is None:
        return {}
    rec = {"source": "vidyutpravah", "url": url, "demand_met_mw": int(round(demand))}
    prev = extract_number(html, FIELDS["prev_demand_met_mw"])
    if prev is not None:
        rec["prev_demand_met_mw"] = int(round(prev))
    price = extract_number(html, FIELDS["exchange_price_rs"])
    if price is not None:
        rec["exchange_price_rs"] = price
    return rec


# MERIT (meritindia.in) state page: numbers ride in server-rendered hidden inputs.
# Despite its id, "AllIndiaDemand" holds the *selected state's* Demand Met — verified
# 2026-07-16: AllIndiaDemand 25,413 = ISGSGen 16,211 + Import_data 9,202 for MH.
MERIT_INPUTS = {
    "demand_met_mw": "AllIndiaDemand",
    "own_generation_mw": "ISGSGen",
    "import_mw": "Import_data",
}


def _merit_input(html: str, input_id: str):
    m = re.search(r'id="' + re.escape(input_id) + r'"\s+value="\s*([\d,]+(?:\.\d+)?)\s*"', html)
    return float(m.group(1).replace(",", "")) if m else None


def fetch_merit(merit_name: str) -> dict:
    """Parse the MERIT portal's state page (failover source). Same contract as above."""
    url = MERIT_URL.format(merit_name=merit_name)
    html = common.http_get(url, headers=BROWSER_HEADERS).decode("utf-8", errors="replace")
    demand = _merit_input(html, MERIT_INPUTS["demand_met_mw"])
    if demand is None:
        return {}
    rec = {"source": "merit", "url": url, "demand_met_mw": int(round(demand))}
    own = _merit_input(html, MERIT_INPUTS["own_generation_mw"])
    imp = _merit_input(html, MERIT_INPUTS["import_mw"])
    if own is not None:
        rec["own_generation_mw"] = int(round(own))
    if imp is not None:
        rec["import_mw"] = int(round(imp))
    return rec


def collect_state(slug: str, slot: str) -> dict:
    """Fetch one state, trying each source in order. Never raises.

    A fetch failure (site down / IP blocked) falls through to the next source;
    only an all-sources outcome is recorded. `error_kind: schema` is reserved for
    a source that RESPONDED but no longer parses — that one needs a human.
    """
    ist = common.now_ist()
    base = {
        "ts_ist": ist.isoformat(timespec="seconds"),
        "ts_utc": ist.astimezone(common.UTC).isoformat(timespec="seconds"),
        "slot": slot,
        "state": slug,
    }
    cfg = STATES[slug]
    schema_broke = []
    errors = []
    for name, fn, arg in (("vidyutpravah", fetch_vidyutpravah, slug),
                          ("merit", fetch_merit, cfg["merit_name"])):
        try:
            fields = fn(arg)
        except Exception as e:  # network/transport — try the next source
            errors.append(f"{name}: {type(e).__name__}")
            log.warning("fetch failed for %s via %s: %s", slug, name, e)
            continue
        if not fields:
            schema_broke.append(name)
            log.error("PARSE FAILED for %s via %s — schema break?", slug, name)
            continue
        if name != "vidyutpravah":
            log.info("%s: primary source down, using %s", slug, name)
        return {**base, "ok": True, **fields}

    if schema_broke:
        return {**base, "ok": False, "error_kind": "schema",
                "error": "parse_failed:" + ",".join(schema_broke)}
    return {**base, "ok": False, "error_kind": "fetch", "error": "; ".join(errors)}


def have_good_slot(records: list[dict], slug: str, slot: str) -> bool:
    """True if we already have a *successful* reading for this state+slot today."""
    return any(
        r.get("state") == slug and r.get("slot") == slot and r.get("ok")
        for r in records
    )


def main() -> int:
    ist = common.now_ist()
    slot = common.slot_key(ist, DEMAND_SLOT_MINUTES)
    day_file = DEMAND_DIR / f"{ist.strftime('%Y-%m-%d')}.jsonl"
    existing = common.read_jsonl(day_file)

    wrote = 0
    schema_break = False
    for slug in STATES:
        if have_good_slot(existing, slug, slot):
            log.info("slot %s already collected for %s — skipping", slot, slug)
            continue
        rec = collect_state(slug, slot)
        common.append_jsonl(day_file, rec)
        wrote += 1
        if rec["ok"]:
            log.info("%s @ %s: %s MW", slug, slot, rec["demand_met_mw"])
        elif rec.get("error_kind") == "schema":
            schema_break = True

    log.info("done: %d record(s) -> %s", wrote, day_file.relative_to(REPO_ROOT))
    return 1 if schema_break else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Belt-and-braces: an unexpected error must not turn the cron permanently red.
        log.exception("unexpected fatal error in fetch_demand")
        sys.exit(0)
