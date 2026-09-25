# Grid Pulse — Collector

Accumulates the on-the-record dataset: **Maharashtra electricity demand** (live, from
vidyutpravah.in) and **weather** (Open-Meteo), one reading per hourly slot, committed back to the repo by
**the Synology NAS** (`run_and_push.py`, every 15 min — see "Where each collector runs").
Stdlib-only — no `pip install`. **Must run on Python 3.8** (the NAS's version): keep
`from __future__ import annotations` at the top of every module.

## Why "collector-first"
There is no historical **hourly per-state** demand feed anywhere (see `../DATA-SOURCES.md`).
So we build our own from now on: poll the live per-state "Demand Met" value and store it.
Daily-granularity backfill (2013→) comes separately from Grid-India PSP reports.

## Scripts

| Script | What it does | Output |
|--------|--------------|--------|
| `fetch_demand.py`  | Scrapes MH live "Demand Met" (MW) from vidyutpravah, failing over to meritindia | `data/raw/demand/YYYY-MM-DD.jsonl` |
| `fetch_weather.py` | Open-Meteo current-hour temp/RH/apparent for MH cities + population-weighted state aggregate | `data/raw/weather/YYYY-MM-DD.jsonl` |
| `backfill_psp.py`  | **One-off/local** (needs `xlrd`): Grid-India daily PSP XLS → per-state daily peak MW + energy MU, FY2023-24→today | `data/history/psp/<state>.jsonl` |
| `run_and_push.py`  | **Production entry point:** runs both collectors, commits new `data/`, pushes (rebases over any other writer) | git commit on `main` |
| `run_nas.sh`       | DSM Task Scheduler wrapper for `run_and_push.py` (logs to `~/gridpulse/collect.log`) | — |
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
- **Schedule:** every 15 min from the NAS (DSM Task Scheduler) — ~4 attempts per hour.
  The **slot guard** (`have_good_slot`) skips a slot that already has a good reading, so
  the extra attempts never duplicate — they only *recover* a slot that failed earlier in
  the hour.
- Want intra-hour shape? Set `DEMAND_SLOT_MINUTES = 15` — the guard and schedule already
  support it (you'd just get ~4× more rows/commits).

## Failure handling
- **Never crashes.** A network failure writes a gap record (`error_kind:"fetch"`) and the
  run continues; the next scheduled attempt re-tries the same slot.
- **Schema break** (a source responded but no longer parses) writes `error_kind:"schema"`
  and makes `fetch_demand` exit **1**. On the NAS nothing turns red — check the data (or
  `~/gridpulse/collect.log`) for `schema` gap records; that is the one failure that must
  not pass silently.

## ⚠️ Where each collector runs (read this first)

| Collector | Runs on | Why |
|---|---|---|
| `fetch_demand` | **NAS** (DS423) via `run_and_push.py` | GitHub runners **cannot reach** vidyutpravah *or* meritindia — 343/343 scheduled attempts failed (2026-07-16 → 08-10) with `URLError`, while the same URLs return HTTP 200 from India at the same moments. Not a UA/WAF issue: browser headers and a second independent portal both failed. |
| `fetch_weather` | **NAS**, same run | Open-Meteo is reachable from anywhere, but one writer for `data/` avoids merge churn. `collect.yml` (Actions) can still run it on demand as a backup. |
| `backfill_psp` | Local, on demand | One-off history top-up. |

Re-test the block any time with the manual **`probe`** workflow (tests both portals,
the real collector, and the Grid-India API from a runner).

**NAS deployment facts:** node-local clone at `~/gridpulse/grid-pulse` (NOT the Synology
Drive-synced copy — Drive syncing a live `.git` would corrupt it). DSM task runs as user
`KrishSachdev`: `sh /var/services/homes/KrishSachdev/gridpulse/grid-pulse/collector/run_nas.sh`.
Push credential = fine-grained PAT (Contents: read+write, `grid-pulse` only) in
`~/.git-credentials`, **expires ~Aug 2027**. `.gitattributes` sets `merge=union` on
`data/**/*.jsonl` so overlapping writers never conflict. Record since 2026-08-10: 100% of
hours captured (verified 2026-09-26).

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
  same URLs 200 OK from India. Both collectors moved to `run_and_push.py` on the NAS;
  `collect.yml`'s schedule is disabled (dispatch-only backup). Cost of the diagnosis:
  ~4 weeks of hourly demand history (weather + the daily PSP series are unaffected).

## cron-job.org pinger — NOT NEEDED (kept for reference)
Only relevant if collection ever moves back to GitHub Actions. The NAS schedule is
deterministic, so this was never set up. GitHub's native cron is best-effort (observed
firing every 1–4 h); the workaround is an external pinger calling `workflow_dispatch`:

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

## GitHub Actions (`collect.yml`) — backup only
Schedule **disabled** since 2026-08-10. Runs `fetch_weather` only, and only when triggered
by hand (Actions → collect → Run workflow) — use it to keep the weather series alive if the
NAS is down. It cannot collect demand (runners are geo-blocked).

## To add more states
Add an entry to `STATES` in `config.py` — both the vidyutpravah slug (verify on
`vidyutpravah.in/state-data/<slug>`) and the `merit_name` (verify on
`meritindia.in/StateWiseDetails?StateName=<name>`) — plus a `WEATHER_POINTS[<slug>]` list.
Commit and push from the PC; the NAS picks it up on its next pull.
