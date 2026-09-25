# Grid Pulse

Live, publicly accountable electricity-demand forecasting for Indian states: collect state-level demand + weather daily, publish next-24h forecasts to git BEFORE the target day, score against actuals, keep a permanent public accuracy scoreboard (model vs persistence and seasonal-naive baselines).

**Start every session by reading `PLAN.md` (phases + checklists — update checkboxes as work lands) and `CONTEXT.md` (research background, source links, decisions, and what is explicitly rejected).**

Conventions:
- Phase 0 (data-source recon → `DATA-SOURCES.md`) comes before any collector code; hourly-feed availability is the project's #1 risk.
- **Collection runs on the Synology NAS, not GitHub Actions** — GitHub runners are geo-blocked from the Indian grid portals (proven 2026-08-10). DSM Task Scheduler runs `collector/run_nas.sh` → `run_and_push.py` every 15 min from a node-local clone at `~/gridpulse/grid-pulse` (never the Drive-synced folder). `collect.yml` is dispatch-only backup. Details: `collector/README.md`.
- Collector code: stdlib-only and **Python 3.8-compatible** (the NAS's version) — keep `from __future__ import annotations` in every module; no 3.9+ features. Slot guard makes every run idempotent.
- Data layout: `data/raw/{demand,weather}/YYYY-MM-DD.jsonl` (IST day), `data/history/psp/<state>.jsonl`, `forecasts/<STATE>/YYYY-MM-DD.json`, `scores/<STATE>/YYYY-MM-DD.json`. Forecasts are immutable once committed — never rewrite one.
- Secrets (any PAT) via env/GitHub secrets, never committed.
- Krish drives git himself: prepare commits, let him push. No Co-Authored-By.
- Owner: Krish Sachdev (krishsachdev18@gmail.com, github.com/KrishSachdev). Portfolio site at `..\new website` gets the work-row once the scoreboard has ≥2 weeks of history.
