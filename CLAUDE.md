# Grid Pulse

Live, publicly accountable electricity-demand forecasting for Indian states: collect state-level demand + weather daily, publish next-24h forecasts to git BEFORE the target day, score against actuals, keep a permanent public accuracy scoreboard (model vs persistence and seasonal-naive baselines).

**Start every session by reading `PLAN.md` (phases + checklists — update checkboxes as work lands) and `CONTEXT.md` (research background, source links, decisions, and what is explicitly rejected).**

Conventions:
- Phase 0 (data-source recon → `DATA-SOURCES.md`) comes before any collector code; hourly-feed availability is the project's #1 risk.
- Python, dependency-light for anything that runs on GitHub Actions cron. Reuse the jam-genome Actions lessons (over-scheduled cron + slot guard + workflow_dispatch pinger fallback — see `..\jam genome\PLAN.md` Phase 1).
- Data layout: `data/raw/YYYY-MM-DD.jsonl`, `data/history/`, `forecasts/<STATE>/YYYY-MM-DD.json`, `scores/<STATE>/YYYY-MM-DD.json`. Forecasts are immutable once committed — never rewrite one.
- Secrets (any PAT) via env/GitHub secrets, never committed.
- Krish drives git himself: prepare commits, let him push. No Co-Authored-By.
- Owner: Krish Sachdev (krishsachdev18@gmail.com, github.com/KrishSachdev). Portfolio site at `..\new website` gets the work-row once the scoreboard has ≥2 weeks of history.
