# Grid Pulse

**On-the-record electricity demand forecasting for Indian states.**

Most demand-forecasting projects show you a backtest: "my model would have scored X on last year's data." Grid Pulse does the opposite. It collects live grid data every hour, and — once forecasting starts — will publish each day's forecast to this public repository **before that day begins**. The git commit history is a tamper-proof timestamp: nobody can quietly improve a forecast after the fact. When the real numbers come in, they get scored against the forecast and against two honest baselines (persistence, seasonal-naive), and the running accuracy record stays public forever, mistakes included.

Maharashtra is the first state. More states are planned once the pipeline is proven.

## Status (26 September 2026) — read this before assuming anything is running

- **Data collection: live and healthy.** A small script on Krish's home NAS (Synology) has been polling live grid data every hour since **10 August 2026**. From that date through 25 September 2026 it captured **100% of hours for both demand and weather (1,128 of 1,128 possible hours each)**. See [`PLAN.md`](PLAN.md) for the full data-quality numbers.
- **Forecasting: not started yet.** There is no model, no forecast files, and no scoreboard in this repository yet. `forecasts/` and `scores/` directories don't exist. Anyone looking for "the forecast" today will not find one — that's the honest state of the project, not a bug.
- **Why publish now, before forecasting exists?** So the *data collection* itself is on the record. The `data/` commit history already proves when each hourly reading was captured.

## Data sources and their terms

| Source | What we take | Terms / notes |
|---|---|---|
| [vidyutpravah.in](https://vidyutpravah.in) (Ministry of Power) | Live per-state "Demand Met" (MW), polled hourly | Public government dashboard, no API key or login. No `robots.txt` is published; we poll at a modest hourly cadence with a descriptive User-Agent and don't hammer the site. |
| [meritindia.in](https://meritindia.in) (Ministry of Power, MERIT portal) | Same live demand figure, used only as a failover when vidyutpravah is unreachable | Same public-dashboard basis as above. |
| [Open-Meteo](https://open-meteo.com) | Hourly temperature, humidity, and apparent temperature for Mumbai, Pune, Nagpur, and Nashik, combined into a population-weighted Maharashtra figure | Free and keyless for non-commercial use per Open-Meteo's terms; no login required. |
| [Grid-India (formerly POSOCO) daily PSP reports](https://www.grid-india.in) | Daily per-state peak demand and energy met, used only for historical backfill (`data/history/psp/`), not live collection | Government-published daily operational reports (XLS). We derive/aggregate from these; we have not re-published the raw government files themselves. |

We publish our own collected readings (`data/raw/`) and derived history (`data/history/`) here. We do not republish anyone else's raw files.

## Data folder layout

```
data/
  raw/
    demand/YYYY-MM-DD.jsonl     # one line per hourly reading attempt, Maharashtra demand (MW)
    weather/YYYY-MM-DD.jsonl    # one line per hourly reading attempt, MH weather
  history/
    psp/maharashtra.jsonl       # daily peak MW + energy MU, backfilled from Grid-India PSP reports, 2023-04-01 onward
```

Filenames are the **IST calendar day** the reading belongs to (India has one timezone, no DST). Each line is a small JSON record. A record that failed to fetch is still written, as a "gap" record (`"ok": false`) — so a missing hour is always visible in the data itself, never silently dropped.

Demand record (successful):
```json
{"ts_ist": "2026-09-25T00:00:02+05:30", "ts_utc": "2026-09-24T18:30:02+00:00",
 "slot": "2026-09-25T00:00", "state": "maharashtra", "source": "vidyutpravah",
 "ok": true, "demand_met_mw": 25669, "prev_demand_met_mw": 25155, "exchange_price_rs": 10.0}
```

Weather record (successful): a weighted `temp_c` / `rh_pct` / `apparent_c` for the hour, plus the per-city breakdown that produced it, under `cities`.

### Loading the data in Python

The data is public and lives on GitHub's raw-content CDN, so you can load it from anywhere without cloning the repo:

```python
import json
import urllib.request

day = "2026-09-25"
url = f"https://raw.githubusercontent.com/KrishSachdev/grid-pulse/main/data/raw/demand/{day}.jsonl"

records = []
with urllib.request.urlopen(url) as resp:
    for line in resp:
        line = line.strip()
        if line:
            records.append(json.loads(line))

good = [r for r in records if r.get("ok")]
print(f"{len(good)}/{len(records)} hours captured on {day}")
print("demand range (MW):", min(r["demand_met_mw"] for r in good), "-", max(r["demand_met_mw"] for r in good))
```

To list which day-files exist without knowing the dates in advance, use the GitHub contents API (public, no token needed):
```
https://api.github.com/repos/KrishSachdev/grid-pulse/contents/data/raw/demand
```

## How collection works

A Python script (`collector/`) runs every 15 minutes on a small home server (a Synology NAS), tries the live government demand portal for Maharashtra, fails over to a second portal if the first is down, fetches matching weather from Open-Meteo, and commits+pushes any new hourly readings straight to this repository — one commit per collection run. It's deliberately simple: stdlib-only Python, no dependencies to install, and it's built to never crash (a failed fetch just writes a gap record and the next attempt tries again). Full details, including why it runs on a home server rather than GitHub's own cloud runners (they're blocked from reaching Indian grid portals), are in [`collector/README.md`](collector/README.md).

## Dashboard

A live dashboard (Maharashtra demand vs last week, daily peaks, collection health, temperature vs demand) is in [`docs/`](docs/). It reads data directly from this repository's raw files, so it's always current wherever it's hosted.

## Roadmap

1. ~~Find a reliable live per-state demand feed~~ — done.
2. ~~Collect demand + weather hourly, prove the pipeline is reliable~~ — done, running since 10 Aug 2026.
3. **Backtest a forecasting model** (persistence and seasonal-naive baselines first, then a proper model) against the accumulated data — not started.
4. Go operational: commit each day's next-24h forecast before that day starts, score it once actuals arrive, keep the scoreboard public and never edit past results.
5. Add more states (Delhi, Gujarat, Tamil Nadu, Uttar Pradesh planned).
6. Publish the honest accuracy record and, eventually, write up the results.

## Licence

Not yet formally declared — see the licensing note in [`PLAN.md`](PLAN.md). In short: the collector code is intended to be MIT-licensed; the data we collect ourselves is intended to be openly reusable with attribution; a couple of upstream sources (noted above) carry their own terms that any reuse should respect.

## Project owner

Krish Sachdev — [github.com/KrishSachdev](https://github.com/KrishSachdev)
