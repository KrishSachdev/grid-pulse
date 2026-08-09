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
| `backfill_psp.py`  | **One-off/local** (needs `xlrd`): Grid-India daily PSP XLS → per-state daily peak MW + energy MU, FY2023-24→today | `data/history/psp/<state>.jsonl` |
| `config.py`        | States, city points/weights, paths, cadence | — |
| `common.py`        | IST time, slot flooring, HTTP-with-retry, JSONL I/O, logging | — |

### Backfill notes (`backfill_psp.py`)
- Lists all files via `POST webapi.grid-india.in/api/v1/file` (`_type: DAILY_PSP_REPORT`), downloads
  from `webcdn.grid-india.in` into `cache/psp/` (gitignored), parses sheet `MOP_E`.
- **XLS exists only from ~Jan 2023 (complete from FY 2023-24)**; older years are PDF-only —
  deep history, if ever needed, comes from the Kaggle CC BY-SA mirror instead.
- Resumable + idempotent: re-running only fetches/parses missing dates, then rewrites the
  output sorted+deduped. Top up history any time with a plain re-run.
- Sanity ranges (peak 1–60 GW, energy 100–2000 MU) refuse implausible parses → gap records
  (`"ok": false`) instead of silent garbage.
- Grid-India serves a broken TLS chain; the script uses an unverified-SSL context (same as
  `curl -k`) for these two hosts only.

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

## ⚠️ Where each collector runs (read this first)

| Collector | Runs on | Why |
|---|---|---|
| `fetch_demand` | **A machine in India** (NAS/PC) via `run_and_push.py` | GitHub runners **cannot reach** vidyutpravah *or* meritindia — 343/343 scheduled attempts failed (2026-07-16 → 08-10) with `URLError`, while the same URLs return HTTP 200 from India at the same moments. Not a UA/WAF issue: browser headers and a second independent portal both failed. |
| `fetch_weather` | GitHub Actions (`collect.yml`) | Open-Meteo is globally reachable; 372 good hours collected. |
| `backfill_psp` | Local, on demand | One-off history top-up. |

Re-test the block any time with the manual **`probe`** workflow (tests both portals,
the real collector, and the Grid-India API from a runner).

## Known issue log
- **2026-07-13 — vidyutpravah blocks GitHub-runner IPs** with the plain collector UA
  (every Actions fetch: `Connection reset by peer`; local fetches fine). Mitigation:
  `fetch_demand` now sends browser-like headers (`BROWSER_HEADERS`). Run the manual
  `probe` workflow to re-test what a runner can reach; if vidyutpravah stays blocked
  from runners entirely, fall back to local collection (Task Scheduler) for hourly +
  Grid-India PSP (reachable check via probe step 4) for daily actuals.
- **2026-07-13 — GitHub cron throttling:** scheduled runs arrive 1–4 h apart despite
  `*/15` (~10–12 runs/day, not 96). Confirmed over 30 days: weather averaged 12.4 of
  24 hours/day. Fix: external pinger (below), or the local runner's own scheduler.
- **2026-08-10 — RESOLVED (root cause): runners are geo/datacenter-blocked from
  Indian grid portals.** Both sources, 343 consecutive failures, zero successes;
  same URLs 200 OK from India. `collect.yml` is now **weather-only** and demand moved
  to `run_and_push.py` on India-side hardware. Cost of the diagnosis: 4 weeks of
  hourly demand history (weather + the 1,199-day daily series are unaffected).

## Deterministic cadence: cron-job.org pinger (one-time setup, ~10 min)
GitHub's native cron is best-effort and was observed firing every 1–4 h. The fix is an
external pinger calling `workflow_dispatch` on a real clock:

1. **Fine-grained PAT** (github.com → Settings → Developer settings → Fine-grained tokens):
   repository access = only `grid-pulse`; permissions = **Actions: Read and write**;
   expiry 1 year. Copy the token.
2. **cron-job.org** (free): create a job, every 15 min, method POST, URL
   `https://api.github.com/repos/KrishSachdev/grid-pulse/actions/workflows/collect.yml/dispatches`
   Headers:
   `Authorization: Bearer <PAT>` · `Accept: application/vnd.github+json` ·
   `Content-Type: application/json` — Body: `{"ref":"main"}`
3. Verify: Actions tab shows `workflow_dispatch` runs arriving every 15 min.
   The slot guard makes the native cron + pinger overlap harmless.

## GitHub Actions (`collect.yml`)
Runs the collectors and commits new `data/` back to the repo (`contents: write`).
`workflow_dispatch` is enabled so an external pinger (cron-job.org) can trigger it for
deterministic timing if the native cron proves too unreliable — the jam-genome fallback.
The bot commits are the operational mechanism; a public repo gets free Actions minutes.

## To add more states
Add a slug to `STATES` in `config.py` (verify it on `vidyutpravah.in/state-data/<slug>`)
and, for weather, a `WEATHER_POINTS[<slug>]` list. Do this only once MH is stable.
