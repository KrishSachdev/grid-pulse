# Grid Pulse — Project Plan

**One-liner:** A live, publicly accountable electricity-demand forecaster for Indian states — publish next-24h hourly demand forecasts *before* the day starts, score them against actuals when they arrive, and keep the running accuracy record public forever.

**Why it's novel (verified July 2026):** Academic studies exist (offline XGBoost state-level demand models, an MIT thesis on data-poor Indian forecasting — see CONTEXT.md) and government dashboards *display* demand, but **nobody runs an open operational system with an on-the-record forecast history**. "My model has been publicly on the record for N days with X% MAPE vs baseline" is a claim no student portfolio makes. The git commit history is the tamper-proof timestamp.

**Status (2026-09-26):** Phase 0 ✅ · Phase 1 ✅ — NAS collecting Maharashtra demand + weather hourly, 100% coverage since 2026-08-10 · **Next: Phase 2 (backtesting)** — not started.

**Deliverables:**
1. An accumulated open dataset of Indian state-level demand + weather
2. A daily operational forecast (Maharashtra first, then ~4 more states)
3. A public scoreboard — model vs honest baselines, updated daily, never edited
4. Dashboard on GitHub Pages; portfolio work-row when live
5. Optional paper #3: "An open operational demand-forecasting system for Indian states" (Krish has one publication — LSTM forecasting, Lex Localis 2025 — this extends that identity from offline to operational)

---

## Phase 0 — Data recon (THE critical phase; do before writing any code)

The whole project stands on finding a reliable hourly (or ≤hourly) per-state demand feed. Verify these candidates in order, in a browser + with curl, and document findings in `DATA-SOURCES.md`.

**✅ PHASE 0 COMPLETE (2026-07-12) — see `DATA-SOURCES.md` for full detail. Outcome: hybrid, no full daily-pivot needed.**

- [x] **NITI Aayog ICED** (https://iced.niti.gov.in) — ❌ **hourly load-curve is DEAD** (all `loadCurve*` endpoints 404; page redirects to home, fires no API calls). API responses are AES-encrypted (key `AHten@VP0W3R`, decrypt recipe in DATA-SOURCES). Only useful bit: `dailyPeakDemand/last30Days` = **national** daily peak MW, 2017→present (bonus, not our hourly source).
- [x] **vidyutpravah.in** — ✅ **PRIMARY live hourly source.** `/state-data/<slug>` server-renders live "Demand Met" (MW); confirmed it updates every ~1–5 min (MH moved 21,097→21,140 MW in 77 s). Plain curl, no key, selector `value_DemandMET_en`. **Collector-first: poll every 15 min → build our own per-state hourly dataset.**
- [x] **Grid-India / POSOCO daily PSP reports** — ✅ posoco.in dead (rebranded → grid-india.in). JSON API `webapi.grid-india.in/api/v1/file` lists daily XLS on `webcdn.grid-india.in`; `MOP_E` sheet = **per-state daily peak demand + energy met** (MH verified), FY 2013-14→present. `TimeSeries` sheet = national 15-min (not per-state). This is the **daily backfill + daily floor** — and it has real history, so the daily model can go on the record immediately.
- [x] **Kaggle** (`aryankhurana1701/state-wise-electricity-consumption-in-india`) — ✅ CC BY-SA 4.0, daily per-state MU, Jan 2013→ (~3700 rows). Raw PSP scrape, v1 (may be stale for recent weeks). Convenience backfill for the daily model; download needs a Kaggle token.
- [x] **Weather:** Open-Meteo — ✅ forecast + archive both verified for Mumbai, keyless, IST-aware. MH points: Mumbai/Pune/Nagpur/Nashik (population-weighted). Use *forecast* weather in operational features, archive for training only.
- [x] **Decision gate:** hourly per-state is scrapeable **live** (vidyutpravah) but has **no historical backfill**; daily per-state has deep backfill (PSP/Kaggle 2013→). → **Keep hourly as the operational target via collector-first, AND run a daily per-state model in parallel that trains on PSP history and goes on the record from day 1.** No full pivot; we get both.
- [x] **Scraping etiquette:** vidyutpravah has no robots.txt (404) — use descriptive User-Agent, 15-min cadence. Grid-India TLS chain is broken (`curl -k`). ICED decrypt key is obfuscation not a licence — conservative about republishing raw dumps (Plan B: publish derived aggregates + scores only).

## Phase 1 — Collector (reuse the jam-genome playbook)

**✅ PHASE 1 COMPLETE — collecting 24/7 from the Synology NAS since 2026-08-10.** Verified 2026-09-26 against the GitHub repo: **47/47 days, 1,128/1,128 hours of both demand and weather captured (100%, zero gaps)**. Demand range in that period 19,183–30,515 MW. Sources: vidyutpravah 1,108 h, MERIT failover 21 h (the failover has earned its keep).

**How it runs now:**
- **Demand + weather → NAS (DS423, `192.168.1.10`).** DSM Task Scheduler, every 15 min, user `KrishSachdev`: `sh /var/services/homes/KrishSachdev/gridpulse/grid-pulse/collector/run_nas.sh` → `collector/run_and_push.py` (collect → commit → push, author `grid-pulse-nas`). Hourly slot grid + slot guard, so 4 attempts/hour and one reading per hour.
- **Node-local clone** at `~/gridpulse/grid-pulse`, deliberately *not* the Synology Drive-synced folder (Drive syncing a live `.git` between PC and NAS would corrupt it). Log: `~/gridpulse/collect.log`.
- **Credential:** fine-grained PAT (Contents: read+write, `grid-pulse` only) stored in `~/.git-credentials` on the NAS. **Expires ~Aug 2027 (1 year from 2026-08-10) — renew before then or pushes stop silently.**
- **NAS Python is 3.8.15** → every collector module starts with `from __future__ import annotations`; don't use 3.9+ features (dict `|`, `removeprefix`, `zoneinfo`, `match`).
- **`.gitattributes`: `data/**/*.jsonl merge=union`** — two writers on the same day-file merge instead of conflicting.
- **GitHub Actions:** `collect.yml` schedule **disabled** (dispatch-only backup for weather if the NAS is down); `probe.yml` = manual diagnostic of what a runner can reach. cron-job.org pinger **not needed** — the NAS schedule is deterministic.

**Checklist:**
- [x] `collector/fetch_demand.py` (vidyutpravah → MERIT failover) + `collector/fetch_weather.py` (Open-Meteo, 4 MH cities, pop-weighted) → `data/raw/{demand,weather}/YYYY-MM-DD.jsonl`. Stdlib-only, retries/backoff, never crash, gap records, schema-break detection.
- [x] Repo live: github.com/KrishSachdev/grid-pulse (public, `main`).
- [x] Hourly collection running from India-side hardware (NAS) — see above.
- [x] **Historical backfill** (`collector/backfill_psp.py`, local one-off, needs `xlrd` + `openpyxl`): `data/history/psp/maharashtra.jsonl` = **1,199 days, 2023-04-01 → 2026-07-15**. XLS only exists from ~Jan 2023 (earlier is PDF-only; the Kaggle CC BY-SA mirror covers 2013+ if ever needed). Peak 20.1–32.3 GW; clean seasonality (Feb–Mar ~29 GW high, July monsoon ~23.4 GW low). **Not topped up since 2026-07-16 — re-run before Phase 2** (resumable; only fetches the missing days).
- [ ] States: Maharashtra only so far; add Delhi, Gujarat, Tamil Nadu, UP (one-line `STATES` / `WEATHER_POINTS` additions — verify slug + MERIT name on both portals first).

**Deployment history (why it runs on the NAS, not Actions):**
- **2026-07-12** — launched on GitHub Actions cron.
- **2026-07-13** — two problems on day 1: demand fetches from runners failed (`Connection reset by peer`) while working from India; GitHub cron throttled to ~8–12 runs/day instead of 96.
- **2026-07-13 → 16** — vidyutpravah itself was down ~3 days. Added the **MERIT failover** (`meritindia.in/StateWiseDetails?StateName=...`; hidden input `AllIndiaDemand` = the state's demand met; cross-checked against vidyutpravah <1%) and browser-like headers.
- **2026-07-16 → 08-10** — **343 of 343 scheduled Actions attempts failed on both portals** while the same URLs returned HTTP 200 from India → **GitHub runners are geo/datacenter-blocked from Indian grid portals**; headers can't fix it. Weather was fine throughout.
- **2026-08-10** — demand collection moved to the NAS (`run_and_push.py`), Python 3.8 compat, union-merge for data files, Actions switched to dispatch-only. First complete 24-hour day the same day; unbroken since.
- **Cost:** hourly demand for ~2026-07-13 → 08-09 is lost for good (no public archive exists). Weather and the daily PSP series are unaffected.

## Phase 2 — Backtesting (offline, honest)

**Not started.** Prerequisites: top up PSP history (stops 2026-07-15 — `python -m collector.backfill_psp --since 2026-07-15`), and backfill Open-Meteo *archive* weather for 2023-04 onward to match the training period (the archive API returns years per request).

- Baselines that must be beaten and must stay on the scoreboard forever: **persistence** (same hour yesterday) and **seasonal-naive** (same hour, same weekday last week).
- Model v1: LightGBM/XGBoost — lags (24h/48h/168h), calendar features (weekday, holiday calendar incl. Indian festivals — Diwali is a famous demand event), weather forecast features (temp/humidity/heat-index; use *forecast* weather in features, not actuals — the operational system won't have actuals).
- Time-series CV (rolling origin), never random splits. Metrics: MAPE + sMAPE + skill vs seasonal-naive.
- Only go operational when v1 beats seasonal-naive out-of-sample by a margin worth publishing.

## Phase 3 — Go operational (the differentiating phase)

- Daily job (e.g. 22:00 IST): generate next-day 24h hourly forecast per state → commit `forecasts/MH/YYYY-MM-DD.json` **before the target day begins**. Commits are the timestamp; forecasts are immutable — never rewritten, wrong ones stay in history.
- Daily scoring job: once actuals land, write `scores/MH/YYYY-MM-DD.json` (per-hour APE, daily MAPE, skill vs both baselines).
- `SCOREBOARD.md` auto-regenerated: rolling 7/30/90-day MAPE, model vs baselines, worst day honestly annotated.

## Phase 4 — Dashboard + portfolio (weeks 6–8)

- GitHub Pages, vanilla HTML/CSS/JS (existing skill): yesterday's forecast-vs-actual curve, rolling scoreboard, live demand ticker, "why was the model wrong on X" notes. Design language can echo the portfolio site.
- Content moments: heat-wave weeks ("AC added N GW"), Diwali evening dip/spike, monsoon cooling effect on demand.
- Add work-row on the portfolio site (`..\new website`) once the scoreboard has ≥2 weeks of history — link when dashboard ships.

## Phase 5 — Stretch

- LSTM/TFT vs LightGBM comparison on the accumulated dataset → the paper.
- Demand–temperature elasticity per state (degree-day analysis).
- More states; a national aggregate forecast.
- Festival-effect quantification (Diwali, Ganesh Chaturthi in MH).

## Risks & honest notes

- **#1 risk is Phase 0:** hourly per-state data may not be cleanly accessible — that's why recon precedes code, and why the daily-granularity pivot is pre-agreed as an acceptable floor.
- **Collection must run from India.** Hosted CI (GitHub runners) is geo-blocked from the grid portals. The NAS is therefore a single point of failure: a power or network outage there means gaps (logged honestly, and weather can be kept alive via the dispatch-only Actions workflow). Also watch the NAS PAT's expiry (~Aug 2027).
- Source format drift (gov portals redesign without notice) — collector must alert on schema breaks (a failed-parse day that goes unnoticed kills the scoreboard's credibility).
- Actuals get revised — score against first-published actuals and note the policy openly.
- A full seasonal cycle takes a year — fine; the scoreboard is meaningful from week 2, and backfill covers seasonality for training.
- India has no DST and one timezone — one genuine mercy in this domain.
- Krish drives git himself; sessions prepare, he commits/pushes.

## Timeline snapshot

| When | What |
|------|------|
| Session 1 | ✅ Phase 0 recon → DATA-SOURCES.md; hourly = GO (live via vidyutpravah collector), daily model also viable with PSP backfill |
| Week 1 (07-12) | ✅ Collector + 1,195-day PSP backfill landed; Actions demand collection turned out to be blocked (see Phase 1 history) |
| Week 5 (08-10) | ✅ Collector moved to the NAS — 100% hourly coverage since |
| Next | Phase 2 backtesting; beat seasonal-naive convincingly |
| After that | Operational forecasts on the record, scoreboard starts |
| Then | Dashboard + portfolio row (once the scoreboard has ≥2 weeks) |
| Ongoing | More states, paper draft when 60–90 days of record exist |
