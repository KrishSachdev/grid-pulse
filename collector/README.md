# Grid Pulse — Collector

Accumulates the on-the-record dataset: **Maharashtra electricity demand** (live, from
vidyutpravah.in) and **weather** (Open-Meteo), one reading per hourly slot, committed
back to the repo by GitHub Actions. Stdlib-only — no `pip install`, runs anywhere with
Python 3.10+.

## Why "collector-first"
There is no historical **hourly per-state** demand feed anywhere (see `../DATA-SOURCES.md`).
So we build our own from now on: poll the live per-state "Demand Met" value and store it.
Daily-granularity backfill (2013→) comes separately from Grid-India PSP reports.

## Scripts

| Script | What it does | Output |
|--------|--------------|--------|
| `fetch_demand.py`  | Scrapes MH live "Demand Met" (MW) from `vidyutpravah.in/state-data/maharashtra` | `data/raw/demand/YYYY-MM-DD.jsonl` |
| `fetch_weather.py` | Open-Meteo current-hour temp/RH/apparent for MH cities + population-weighted state aggregate | `data/raw/weather/YYYY-MM-DD.jsonl` |
| `config.py`        | States, city points/weights, paths, cadence | — |
| `common.py`        | IST time, slot flooring, HTTP-with-retry, JSONL I/O, logging | — |

## Run locally
```bash
# from the repo root (the "grid pulse" folder)
python -m collector.fetch_demand
python -m collector.fetch_weather
```
Files are keyed by the IST calendar day; each line is one reading.

## Record schema

**Demand** (`data/raw/demand/<day>.jsonl`):
```json
{"ts_ist":"2026-07-12T19:11:29+05:30","ts_utc":"2026-07-12T13:41:29+00:00",
 "slot":"2026-07-12T19:00","state":"maharashtra","source":"vidyutpravah",
 "url":"https://vidyutpravah.in/state-data/maharashtra","ok":true,
 "demand_met_mw":23594,"prev_demand_met_mw":24727,"exchange_price_rs":4.58}
```
- `demand_met_mw` — live state Demand Met, the forecast target.
- `prev_demand_met_mw` — vidyutpravah's "same time yesterday" figure (a free persistence reference).
- Gap record on failure: `{"ok":false,"error_kind":"fetch|schema","error":"..."}` (no demand field).

**Weather** (`data/raw/weather/<day>.jsonl`): weighted `temp_c` / `rh_pct` / `apparent_c`
for the hour, plus the per-city breakdown under `cities`.

## Cadence & the slot guard
- **Sampling:** hourly (`DEMAND_SLOT_MINUTES = 60`). One reading per state per hour.
- **Cron:** every 15 min (`.github/workflows/collect.yml`). GitHub skips many cron slots,
  so we oversample ~4× per hour. The **slot guard** (`have_good_slot`) skips a slot that
  already has a good reading, so over-scheduling never duplicates — it only *recovers*
  slots that failed earlier in the hour.
- Want intra-hour shape? Set `DEMAND_SLOT_MINUTES = 15` — the guard and cron already
  support it (you'd just get ~4× more rows/commits).

## Failure handling
- **Never crashes.** A network failure writes a gap record (`error_kind:"fetch"`) and the
  run continues; the next cron attempt re-tries the same slot.
- **Schema break** (the `value_DemandMET_en` span vanished/changed) writes
  `error_kind:"schema"` and makes `fetch_demand` exit **1**, which the workflow turns into
  a red run — the one failure that must not pass silently.

## GitHub Actions (`collect.yml`)
Runs the collectors and commits new `data/` back to the repo (`contents: write`).
`workflow_dispatch` is enabled so an external pinger (cron-job.org) can trigger it for
deterministic timing if the native cron proves too unreliable — the jam-genome fallback.
The bot commits are the operational mechanism; a public repo gets free Actions minutes.

## To add more states
Add a slug to `STATES` in `config.py` (verify it on `vidyutpravah.in/state-data/<slug>`)
and, for weather, a `WEATHER_POINTS[<slug>]` list. Do this only once MH is stable.
