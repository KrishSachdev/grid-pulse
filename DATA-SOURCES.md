# Grid Pulse — Data Sources (Phase 0 recon)

**Recon date:** 2026-07-12. Verified from a browser + `curl` + decrypting/parsing real responses.
All findings below were confirmed against live endpoints, not assumed from docs.

## TL;DR / Decision gate

- **An hourly per-state demand feed DOES exist — but only *live*, not historical.** `vidyutpravah.in` server-renders each state's live "Demand Met" (MW) and it updates every ~1–5 min (measured: Maharashtra moved 21,097 → 21,140 MW in 77 s). So we build our own hourly per-state dataset from now on — the **collector-first** pattern, exactly as the plan anticipated. **No full pivot to daily needed.**
- **Historical hourly per-state backfill is NOT cleanly available** anywhere I could find. ICED's hourly load-curve endpoints are dead (404, page redirects to home); Grid-India's 15-min TimeSeries is national-only.
- **Daily per-state has deep, guaranteed backfill (2013 →)** via Grid-India PSP reports (and a mirror Kaggle set). So the **daily-granularity model can train immediately and go on the record from day 1**, while the **hourly model accumulates live** and becomes meaningful in a few weeks.

**Recommended plan (hybrid, both on the record):**
1. **Live hourly per-state → vidyutpravah collector** (primary operational target). Maharashtra first.
2. **Daily per-state peak + energy → Grid-India PSP** (has backfill 2013→; the pre-agreed floor, but we get it *and* hourly).
3. **Weather → Open-Meteo** (forecast features + historical archive).
4. Kaggle POSOCO scrape = convenience backfill for the daily model (CC BY-SA 4.0).
5. ICED `dailyPeakDemand` = bonus national daily peak series (2017→) for a national aggregate / sanity check.

---

## 1. vidyutpravah.in — LIVE per-state demand ✅ PRIMARY (hourly, collector-first)

- **What:** Ministry of Power live grid page. Per-state page server-renders current "State's Demand Met" in MW.
- **URL pattern:** `https://vidyutpravah.in/state-data/<state-slug>` (e.g. `/state-data/maharashtra`, `/state-data/gujarat`, `/state-data/delhi`, `/state-data/tamil-nadu`, `/state-data/uttar-pradesh`). All 30+ states/UTs linked from the homepage.
- **Access:** plain `GET`, no key, no JS execution, no login. ~12 KB HTML per state page. Values are in the server-rendered HTML (not an XHR), so a simple fetch + parse works.
- **Extraction (verified selectors):**
  - `value_DemandMET_en` → **current live Demand Met (MW)** ← this is the target series.
  - `value_PrevDemandMET_en` → same-time-yesterday Demand Met (MW) (a free persistence baseline reference).
  - `value_PrevExchangePrice_en` → exchange price (Rs/unit); `value_PowerShortage_en` → shortage.
  - Regex that worked: `value_DemandMET_en[^>]*>\s*<span[^>]*>\s*([0-9,]+)\s*&nbsp;MW`
- **Cadence:** live snapshot, refreshes every ~1–5 min (confirmed it changes within ~1 min). **Collector plan: poll every 15 min**, timestamp on our side (IST), store the instantaneous MW. Aggregate/resample to hourly for modelling.
- **Robots/etiquette:** `robots.txt` returns 404 (none published). Still: identify via a descriptive User-Agent, keep to 15-min cadence (well below their refresh), don't hammer. It's a public MoP dashboard.
- **Gotchas / to watch in Phase 1:**
  - Homepage `value_maharashtra` span is JS-filled (empty in static HTML) — **use the per-state `/state-data/` pages, which ARE server-rendered**, not the homepage map.
  - Value is instantaneous, not an hourly integral — resampling policy (e.g. mean of the 4 quarter-hour polls, or the on-the-hour reading) must be fixed and documented for the scoreboard to be honest.
  - Schema-break alerting: if `value_DemandMET_en` disappears or parses to non-numeric, the collector must log a gap and alert (a silent parse failure would rot the dataset).

## 2. Grid-India PSP daily reports (ex-POSOCO) — daily per-state ✅ BACKFILL + daily floor

- **posoco.in is dead** (502, rebranded). New home: **grid-india.in** (Grid Controller of India Ltd).
- **Two working access paths** (use the JSON API — it's cleaner and gives direct CDN file paths):

  **(a) JSON API (preferred):**
  - List files: `POST https://webapi.grid-india.in/api/v1/file`  body `{"_source":"GRDW","_type":"DAILY_PSP_REPORT"}` → JSON array of files with `PeriodYear`, `PeriodMonth`, `Title_` (e.g. `11.07.26_NLDC_PSP`), `MimeType`, `FilePath` (e.g. `files/grdw/2026/07/11.07.26_NLDC_PSP_854.xls`).
  - Download: `https://webcdn.grid-india.in/<FilePath>` (HTTP 200, no auth). Latest available at recon: **11.07.26** (yesterday), so ~1-day lag.
  - Page config (how the type is discovered): `POST .../api/v1/page` body `{"_source":"GRDW","_relPath":"/en/reports/daily-psp-report"}` → `FileType:"DAILY_PSP_REPORT"`.
  - Note the site is a React SPA with a **broken TLS chain** (`curl -k` / cert-ignore needed; the in-app browser refused to navigate to it). API calls over `curl -k` work fine.

  **(b) Legacy file portal (fallback):** `https://report.grid-india.in/index.php?p=Daily+Report/PSP+Report/<FY>/<Month+Year>` lists `DD.MM.YY_NLDC_PSP.xls` / `.pdf`; direct file at `https://report.grid-india.in/ReportData/Daily Report/PSP Report/<FY>/<Month YYYY>/<DD.MM.YY>_NLDC_PSP.xls`. FY folders **2013-2014 → 2025-2026** all present.

- **Contents of each daily XLS** (parsed with `xlrd`; `.xls` is real OLE2, not HTML):
  - Sheet **`MOP_E`** — per-region + **per-state** rows: Peak Demand Met (MW), Peak Shortage, Energy Met (MU), Drawal Schedule, etc. Maharashtra row verified: **Peak Demand Met 25,992 MW, Energy Met 563.9 MU** (11.07.26). This is the per-state DAILY series with 2013→ backfill.
  - Sheet **`TimeSeries`** — **national** 15-min interval: Demand Met (MW), plus fuel-mix (Nuclear/Wind/Solar/Hydro/Gas/Thermal). National only — *not* per-state hourly. Useful for a national aggregate forecast and for fuel-mix context, not for MH-hourly.
- **Backfill:** for the daily per-state model, pull the `MOP_E` Maharashtra row across the FY folders (2013→). ~1-day publication lag, so live daily actuals also come from here.
- **Licence/redistribution:** government-published operational reports. Safe to derive/forecast from; if we ever republish raw XLS dumps, check Grid-India terms first (Plan B: publish only our derived aggregates + scores).

## 3. NITI Aayog ICED — hourly per-state ❌ DEAD; national daily ✅ bonus

- **Backend:** `https://icedapi.niti.gov.in/v1`. Angular SPA (`iced.niti.gov.in`).
- **Responses are AES-encrypted client-side** (this is why naive scraping "returns gibberish"):
  - Format = CryptoJS `AES.decrypt(text, passphrase)` → OpenSSL "Salted__" (base64), **AES-256-CBC, MD5 key-derivation**.
  - Passphrase is hard-coded in the bundle: `AHten@VP0W3R` (`environment.KEY`).
  - Decrypt recipe (verified): `curl ... | tr -d '"' | openssl enc -aes-256-cbc -d -a -A -md md5 -pass pass:'AHten@VP0W3R'` → JSON. (It's obfuscation, not access control — but note it's undocumented and could change without notice.)
- **What works:**
  - `GET /v1/dailyPeakDemand/last30Days` → **national** daily peak demand (MW). Name is a misnomer: returns full history **2017-04-01 → present** (3385 daily points). Shape: `[[dates…],[[…values…]]]`.
  - `GET /v1/infographics` (200, encrypted) and other overview endpoints.
- **What's DEAD (the ones we actually wanted):** `loadCurveHourlyState`, `loadCurveHourlyNational`, `loadCurveFilters`, `demandTableDataForYear`, `loadCurveDuration*` — **all 404** on the live server (paths taken verbatim from the current `main.js` bundle). The load-curve page itself redirects to `/` and fires **zero** API calls. Conclusion: **ICED's hourly load-curve feature is currently non-functional; do not depend on it for hourly per-state.**
- **Etiquette/terms:** government portal; modest cadence; treat as read-for-derived-analysis. The encryption key is not a licence — be conservative about redistributing decrypted dumps.

## 4. Kaggle — `aryankhurana1701/state-wise-electricity-consumption-in-india` ✅ convenience backfill

- **Licence:** **CC BY-SA 4.0** (redistributable with attribution + share-alike). Usability 0.94.
- **Content:** raw POSOCO/PSP scrape — **daily** electricity demand (Mega Units) **per state/UT**, **Jan 2013 →**, ~3700 rows × 39 cols (states + `Total Consumption`). "No transformations, no interpolation" — raw, some missing/inconsistent cells.
- **Use:** ready-made daily per-state backfill so we don't have to parse 12 years of PSP XLS ourselves. It IS the PSP data, pre-collated. **But it's version 1 (may be stale for recent weeks)** — so: Kaggle for the deep history, Grid-India PSP for current/live daily.
- **Access:** metadata via `https://www.kaggle.com/api/v1/datasets/view/<owner>/<slug>` (public). File download needs a Kaggle API token (`kaggle.json`) — Krish to provide if we use it, or we skip it and backfill straight from PSP.

## 5. Open-Meteo — weather ✅

- **Forecast:** `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&hourly=temperature_2m,relative_humidity_2m,apparent_temperature&forecast_days=2&timezone=Asia/Kolkata` — keyless, hourly, IST-aware. Verified for Mumbai.
- **Historical archive:** `https://archive-api.open-meteo.com/v1/archive?...&start_date=..&end_date=..&hourly=temperature_2m,relative_humidity_2m` — verified.
- **MH population-weighted points (plan):** Mumbai (19.076, 72.877), Pune (18.520, 73.857), Nagpur (21.146, 79.088), Nashik (19.997, 73.789). Weight by city/population share for a state temperature/heat-index feature.
- **Important:** operational features must use *forecast* weather (what we'll have at forecast time), archive only for training/backfilling features — never leak actual weather into the operational model.

---

## Endpoint quick-reference (copy-paste)

```
# vidyutpravah live MH demand (MW)
curl -s -A "grid-pulse/0.1 (+github.com/KrishSachdev)" https://vidyutpravah.in/state-data/maharashtra
#   -> parse span.value_DemandMET_en  (current),  span.value_PrevDemandMET_en (same-time yesterday)

# Grid-India PSP: list daily files
curl -sk -X POST -H "Content-Type: application/json" -H "Origin: https://grid-india.in" \
  -d '{"_source":"GRDW","_type":"DAILY_PSP_REPORT"}' https://webapi.grid-india.in/api/v1/file
#   -> download https://webcdn.grid-india.in/<FilePath>  ; xlrd -> sheet MOP_E (per-state), TimeSeries (national 15-min)

# ICED national daily peak (2017->), AES-encrypted
curl -s -H "Origin: https://iced.niti.gov.in" -H "Referer: https://iced.niti.gov.in/" \
  https://icedapi.niti.gov.in/v1/dailyPeakDemand/last30Days \
  | tr -d '"' | openssl enc -aes-256-cbc -d -a -A -md md5 -pass pass:'AHten@VP0W3R'

# Open-Meteo forecast (Mumbai)
curl -s "https://api.open-meteo.com/v1/forecast?latitude=19.076&longitude=72.877&hourly=temperature_2m,relative_humidity_2m,apparent_temperature&forecast_days=2&timezone=Asia/Kolkata"
```

## Open questions for Phase 1
- vidyutpravah exact refresh cadence & whether the value is a live instantaneous MW vs a short rolling average — measure by polling every 1 min for an hour; fix the hourly resampling rule before any forecast is committed.
- Does vidyutpravah "Demand Met" reconcile with PSP daily peak/energy for MH? (cross-validate our accumulated hourly against PSP daily totals — a built-in honesty check.)
- Confirm the ICED decrypt key is stable over time (it's a client constant; low priority since ICED isn't our hourly source).
- Grid-India TLS chain is broken — pin/verify or accept `-k`; note it in the collector.
