"""Fetch weather for each state's population-weighted city points (Open-Meteo).

For every state we pull the current-hour temperature / relative-humidity / apparent
temperature at each configured city, then compute a population/load-weighted state
aggregate. One record per state per hourly slot -> data/raw/weather/YYYY-MM-DD.jsonl.

Why current-hour actuals here (not the forecast horizon): weather is fully backfillable
from Open-Meteo's archive API, so the only thing we can't reconstruct later is a clean,
demand-aligned hourly series captured on the same clock as the demand collector. The
operational *forecast* features (no-leakage) are built in Phase 3.

Stdlib only. Same never-crash / idempotent-per-slot contract as fetch_demand.

Run:  python -m collector.fetch_weather      (from the repo root)
"""
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import common
from collector.config import (
    OPEN_METEO_FORECAST,
    REPO_ROOT,
    WEATHER_DIR,
    WEATHER_POINTS,
    WEATHER_SLOT_MINUTES,
)

log = common.get_logger("fetch_weather")

HOURLY_VARS = "temperature_2m,relative_humidity_2m,apparent_temperature"


def fetch_city_hour(lat: float, lon: float, hour_iso: str) -> dict | None:
    """Return {temp_c, rh_pct, apparent_c} for the given hour, or None if unavailable."""
    url = OPEN_METEO_FORECAST + "?" + urlencode({
        "latitude": lat,
        "longitude": lon,
        "hourly": HOURLY_VARS,
        "past_days": 1,       # ensure the current hour is present even early in the day
        "forecast_days": 1,
        "timezone": "Asia/Kolkata",
    })
    data = json.loads(common.http_get(url))
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if hour_iso not in times:
        return None
    i = times.index(hour_iso)
    return {
        "temp_c": hourly["temperature_2m"][i],
        "rh_pct": hourly["relative_humidity_2m"][i],
        "apparent_c": hourly["apparent_temperature"][i],
    }


def collect_state(slug: str, slot: str) -> dict:
    """Fetch all city points for a state and build the weighted aggregate. Never raises."""
    ist = common.now_ist()
    hour_iso = ist.strftime("%Y-%m-%dT%H:00")
    base = {
        "ts_ist": ist.isoformat(timespec="seconds"),
        "slot": slot,
        "state": slug,
        "source": "open-meteo",
        "hour_ist": hour_iso,
    }

    cities = []
    for p in WEATHER_POINTS[slug]:
        try:
            vals = fetch_city_hour(p["lat"], p["lon"], hour_iso)
        except Exception as e:
            log.warning("weather fetch failed for %s/%s: %s", slug, p["city"], e)
            vals = None
        if vals is None:
            continue
        cities.append({"city": p["city"], "weight": p["weight"], **vals})

    if not cities:
        return {**base, "ok": False, "error": "no_city_data"}

    # Weighted aggregate over the cities we actually got (renormalise weights).
    wsum = sum(c["weight"] for c in cities)
    def wavg(key):
        return round(sum(c[key] * c["weight"] for c in cities) / wsum, 2)

    return {
        **base,
        "ok": True,
        "temp_c": wavg("temp_c"),
        "rh_pct": wavg("rh_pct"),
        "apparent_c": wavg("apparent_c"),
        "n_cities": len(cities),
        "cities": cities,
    }


def have_good_slot(records: list[dict], slug: str, slot: str) -> bool:
    return any(
        r.get("state") == slug and r.get("slot") == slot and r.get("ok")
        for r in records
    )


def main() -> int:
    ist = common.now_ist()
    slot = common.slot_key(ist, WEATHER_SLOT_MINUTES)
    day_file = WEATHER_DIR / f"{ist.strftime('%Y-%m-%d')}.jsonl"
    existing = common.read_jsonl(day_file)

    wrote = 0
    for slug in WEATHER_POINTS:
        if have_good_slot(existing, slug, slot):
            log.info("slot %s already collected for %s — skipping", slot, slug)
            continue
        rec = collect_state(slug, slot)
        common.append_jsonl(day_file, rec)
        wrote += 1
        if rec["ok"]:
            log.info("%s @ %s: %.1f°C (feels %.1f), RH %.0f%% [%d cities]",
                     slug, slot, rec["temp_c"], rec["apparent_c"], rec["rh_pct"], rec["n_cities"])

    log.info("done: %d record(s) -> %s", wrote, day_file.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.exception("unexpected fatal error in fetch_weather")
        sys.exit(0)
