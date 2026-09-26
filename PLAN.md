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

## Data-quality check — 2026-09-26 (full dataset, downloaded fresh from GitHub)

Ran a Python check over every file in `data/raw/demand/` and `data/raw/weather/` on GitHub (77 day-files each, **2026-07-12 → 2026-09-26**, 1,528 demand + 1,612 weather attempt-records). Numbers below are from that check, not from memory:

- **Hours captured, full history:** demand 1,135 ok readings / 1,224 possible hours in the 51 calendar days that have any data (92.7%) — the shortfall is entirely the known 2026-07-13→08-09 GitHub-runner geo-block (see Phase 1 history) plus today's in-progress day, not a new problem. Weather: 1,504 / 1,848 (81.3%) over the same span, same known-cause days plus the pre-NAS Actions cron-throttling that also hit weather.
- **NAS era only (2026-08-10 → 2026-09-25, 47 full days) — independently re-verified:** **demand 1,128/1,128 hours (100%) and weather 1,128/1,128 hours (100%).** Matches the Phase 1 claim above exactly, from a fresh download rather than the earlier check.
- **Gaps:** all gap records are honest (`"ok": false`) — demand 393 gaps, all `error_kind: "fetch"` (pre-NAS connection failures); weather 108 gaps, mostly early-July `"no_city_data"` transients. No silent drops: every missing hour has a gap record explaining why.
- **Duplicates:** demand has **zero** duplicate hourly slots (1,135 unique slots for 1,135 ok readings). Weather has **exactly one**: slot `2026-08-10T01:00` was written twice, 9 minutes apart, both `ok: true` with the identical temperature (24.94°C) — landed on the day collection cut over from Actions to the NAS, harmless (same value), but worth knowing the slot guard wasn't airtight across that one cutover moment. No other duplicates found anywhere in either dataset.
- **Impossible values / outliers:** none. Demand range 19,183–30,515 MW, entirely inside a plausible Maharashtra band (never below ~19 GW or above ~31 GW — no negative, zero, or absurd values). Weather temperature range 23.1–31.2°C, plausible for the four MH cities year-round. No missing `demand_met_mw`/`temp_c` fields on any `ok: true` record, no non-numeric values.
- **Units:** demand is in MW (instantaneous "Demand Met", not an energy total — documented in `collector/README.md`); weather is °C (temp/apparent) and % (relative humidity). Consistent across every record checked.
- **Demand vs weather time alignment:** every one of the 1,135 demand hourly slots has a matching weather reading for the same slot (zero orphans). `ts_ist` and `ts_utc` on every demand record represent the same instant (checked to the second, 1,135/1,135 agree) — the UTC/IST conversion is correct. Filenames are the **IST calendar day** as documented (not UTC) — checked all 1,135 demand records, zero mismatches between a record's filename day and its own IST slot day, so there's no day-boundary bucketing bug (unlike a past gotcha on a different project).
- **Conclusion:** the dataset is clean enough to build on. The only real gap is the well-understood pre-NAS period; since the NAS took over on 2026-08-10 the pipeline has been exactly as good as claimed.

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

## Licence note — 2026-09-26 (for Krish to decide; no LICENSE file added)

The repo currently has no licence, so by default nobody else may legally reuse any of it. Suggestion, not a decision:

- **Code (`collector/`, `docs/`):** MIT is the usual choice for a small open project like this — permissive, one paragraph, no obligations beyond keeping the copyright notice.
- **Data we collect ourselves (`data/raw/`, `data/history/`):** consider CC BY 4.0 (free reuse with attribution) — it's our own collected readings, not a republish of someone else's file.
- **Upstream terms to respect regardless of our own licence choice:** vidyutpravah/MERIT are public MoP dashboards with no published redistribution terms (be conservative, cite the source); Open-Meteo is free/keyless for non-commercial use; Grid-India PSP reports are government daily reports we derive from but don't republish raw; the Kaggle mirror mentioned in `DATA-SOURCES.md` is CC BY-SA 4.0 if it's ever used directly.

Krish: add a `LICENSE` file (and a licence line in `README.md`) once you've picked one — intentionally not added automatically here.

## Collector code review — 2026-09-26 (read-only, no changes made)

Read `common.py`, `fetch_demand.py`, `fetch_weather.py`, `run_and_push.py`, `backfill_psp.py`, `config.py` end to end looking for real bugs. **No clear bugs found** — the slot guard, retry/backoff, gap-record-on-failure, and schema-break signalling all work as documented, and that's borne out by the 100% NAS-era coverage. Two things worth knowing (not code bugs, no fix applied):

- **The one weather duplicate found in the data-quality check (`2026-08-10T01:00`, two identical `ok:true` readings 9 minutes apart)** is explained by the architecture, not a logic error: the slot guard only sees one writer's local file before it commits. On 2026-08-10 itself — the day collection cut over from the Actions bot to the NAS — it's plausible two writers both checked the slot as empty before either pushed, and `data/**/*.jsonl merge=union` kept both lines rather than deduping. Not a risk going forward: the Actions weather schedule has been disabled since that day, so there's only one writer now.
- **A schema break in the primary source (vidyutpravah) would go unreported as long as the MERIT failover keeps working** — `collect_state()` returns success on the first source that parses, so a permanently broken primary with a working failover produces no alert, just a quiet, permanent shift to `source: "merit"`. Worth a glance at the `sources` breakdown occasionally (currently 1,114 vidyutpravah / 21 merit — healthy). Not fixed here: it's a monitoring gap, not a data-corrupting bug, and a real fix (separately logging a primary-source failure even when the failover succeeds) is a small design change, not a one-line fix — left for Krish to decide rather than changed unasked.

No code was edited. If either of the above is ever worth fixing, remember: **the NAS needs a `git pull` in its node-local clone (`~/gridpulse/grid-pulse`) before any collector code change takes effect** — pushing from the PC alone does nothing until the NAS pulls.

## README + dashboard — 2026-09-26

- `README.md` added at the repo root (previously missing) — plain-language what/why, honest current status (collecting since 10 Aug, forecasting not started), data source terms, folder layout with a Python load snippet, how collection works, and the roadmap.
- `docs/` added (first built as `site/`, renamed so GitHub Pages can serve it from `main` / `docs`) — a static, no-build-step dashboard (plain HTML/CSS/JS + inline SVG, no CDN) that fetches straight from `raw.githubusercontent.com`, so it stays fresh wherever it ends up hosted (e.g. GitHub Pages later). Shows latest-day-vs-last-week demand, a daily peak trend, a collection-health strip, temperature vs demand, and a last-updated time. See `docs/README.md` for details before turning on Pages.
- Review fixes the same night (maintenance chat): the folder was renamed `site/` → `docs/`, because GitHub Pages can only serve the repo root or `/docs` (not `/site`). The chart axes now hug the data (they ran to 50,000 MW for ~30,000 MW of demand). Today counts only the hours that have started, so the health strip, coverage and "full days" no longer call a normal night "mostly missed". Checked in the browser: 100% coverage, 13/13 full days, today 4/4 hours so far, zero console errors.
- **To publish (Krish):** `git pull`, commit, push, then Settings → Pages → Deploy from a branch → `main` / `/docs`.

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
