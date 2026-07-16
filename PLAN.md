# Grid Pulse — Project Plan

**One-liner:** A live, publicly accountable electricity-demand forecaster for Indian states — publish next-24h hourly demand forecasts *before* the day starts, score them against actuals when they arrive, and keep the running accuracy record public forever.

**Why it's novel (verified July 2026):** Academic studies exist (offline XGBoost state-level demand models, an MIT thesis on data-poor Indian forecasting — see CONTEXT.md) and government dashboards *display* demand, but **nobody runs an open operational system with an on-the-record forecast history**. "My model has been publicly on the record for N days with X% MAPE vs baseline" is a claim no student portfolio makes. The git commit history is the tamper-proof timestamp.

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

**🟡 IN PROGRESS (2026-07-12): MH live collectors built, tested against live sources, workflow written. Not yet on GitHub (Krish to commit/push + enable Actions). Backfill still TODO.**

- [x] `collector/fetch_demand.py` (vidyutpravah MH `value_DemandMET_en`) + `collector/fetch_weather.py` (Open-Meteo, 4 MH cities, pop-weighted) → `data/raw/{demand,weather}/YYYY-MM-DD.jsonl`. Stdlib-only, retries/backoff, never crash, gap records, schema-break detection (exit 1). Verified live: MH 23,594 MW; weather 27.0°C feels-30.4. Slot guard + prev/current parser disambiguation unit-checked.
- [x] **GitHub Actions cron** (`.github/workflows/collect.yml`): sample hourly, cron every 15 min (~4× oversample vs Actions' ~75% skip), slot guard = idempotent; `workflow_dispatch` enabled for cron-job.org pinger fallback; auto-commits data back (`contents: write`). Schema break → red run.
- [x] **Repo live:** github.com/KrishSachdev/grid-pulse (public, main). Smoke-test run green — and it correctly *skipped* the already-collected 19:00 slot (slot guard proven in prod). Node-20 deprecation fixed (checkout@v5 / setup-python@v6).
- [x] Cron fires and bot commits land — **but two problems found on day 1 (2026-07-13):**
  **(a) vidyutpravah resets connections from GitHub-runner IPs** (every Actions demand fetch = ECONNRESET while local fetches succeeded; weather unaffected). Mitigations shipped: browser-like headers in `fetch_demand`; manual `probe` workflow to test what runners can reach (vidyutpravah×2 UAs, real collector, grid-india webapi, meritindia alternate). Verdict pending a probe run when the site is up.
  **(b) GitHub cron throttled to ~1 run per 1–4 h** (8/day, not 96) → cron-job.org pinger required (setup guide in `collector/README.md`; needs Krish: fine-grained PAT + free pinger account).
  Also observed: vidyutpravah itself went down (HTTP 500) evening of 07-13 — site flakiness is real; gap records + oversampling are the right design. If runners stay hard-blocked: local Task Scheduler collection for hourly + PSP daily actuals from Actions (probe step 4 tests it).
  **Update 2026-07-16:** vidyutpravah stayed down ~3 days (back, but flaky) and the 07-13 fixes were never pushed → 3 days of demand gaps from Actions (weather fine, gap-logging exemplary). **Failover source added: MERIT portal** (`meritindia.in/StateWiseDetails?StateName=...`, hidden input `AllIndiaDemand` = state demand met; cross-validated against vidyutpravah <1%). `fetch_demand` now tries vidyutpravah → MERIT; record's `source` field says which answered. PSP history topped up to 07-15 (1,199 days). **Still pending Krish: push fixes, run probe once, set up pinger.**
- [ ] States: start Maharashtra only; add Delhi, Gujarat, Tamil Nadu, UP once MH is stable (one-line `STATES`/`WEATHER_POINTS` additions).
- [x] **Historical backfill DONE** (`collector/backfill_psp.py`, local one-off, needs `xlrd`+`openpyxl`): Grid-India webapi lists ALL 6,181 PSP files (2013→). **XLS only exists from ~Jan 2023** (earlier = PDF-only; Kaggle CC BY-SA mirror covers deep history if ever needed). **`data/history/psp/maharashtra.jsonl`: 1,195/1,195 listed days parsed (2023-04-01 → 2026-07-11), only 3 calendar days have no XLS anywhere.** Peak 20.1–32.3 GW, mean 26.5 GW; monthly means show textbook seasonality (Feb–Mar high ~29 GW, July monsoon low ~23.4 GW). xlsx era + legacy-portal 404 fallback handled. Resumable — re-run any time to top up.

## Phase 2 — Backtesting (offline, honest)

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
- Source format drift (gov portals redesign without notice) — collector must alert on schema breaks (a failed-parse day that goes unnoticed kills the scoreboard's credibility).
- Actuals get revised — score against first-published actuals and note the policy openly.
- A full seasonal cycle takes a year — fine; the scoreboard is meaningful from week 2, and backfill covers seasonality for training.
- India has no DST and one timezone — one genuine mercy in this domain.
- Krish drives git himself; sessions prepare, he commits/pushes.

## Timeline snapshot

| When | What |
|------|------|
| Session 1 | ✅ Phase 0 recon → DATA-SOURCES.md; hourly = GO (live via vidyutpravah collector), daily model also viable with PSP backfill |
| Week 1 | Collector live on Actions (MH), backfill landed |
| Weeks 2–4 | Backtesting; beat seasonal-naive convincingly |
| Week 4+ | Operational forecasts on the record, scoreboard starts |
| Weeks 6–8 | Dashboard + portfolio row |
| Ongoing | More states, paper draft when 60–90 days of record exist |
