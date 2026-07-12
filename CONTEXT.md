# Context — how Grid Pulse came to be

Written 2026-07-11 in the portfolio-website Claude Code session. This file exists so future sessions (or future Krish) have the background without that chat.

## Who's building this

Krish Sachdev — 5th year (of 6) B.Tech Integrated Data Science, MPSTME NMIMS Mumbai. Python/TensorFlow/LangChain. One publication: Enhanced LSTM Models for Short-Horizon Forecasting, Lex Localis 2025 (https://lex-localis.org/index.php/LexLocalis/article/view/801693) — Grid Pulse deliberately extends this forecasting identity from an offline paper to a live operational system. Maexadata internship ended July 2026, so he has time. GitHub: github.com/KrishSachdev. Portfolio site: `..\new website` (gets a Grid Pulse work-row once the scoreboard is live).

## Portfolio state at project start (why this project)

- **jam genome** (`..\jam genome`) — Mumbai traffic propagation; collector built and validated, in passive data-collection mode for weeks. Grid Pulse reuses its GitHub-Actions-collector playbook (including the hard-won lesson that Actions cron skipped ~75% of slots → over-schedule + slot guard + external workflow_dispatch pinger as fallback).
- **LOCAL** (`..\LOCAL`) — local AI knowledge assistant, being debugged/shipped in a separate chat. Don't duplicate work on it here.
- **ride-sharing-app-main** — done, on GitHub, on the resume.
- **COMPRESSION** ("Compress Lab") — finished-ish PWA, unshipped; standing quick-win idea: put it on GitHub Pages.
- Capstone (Autonomous Financial Research Agent) — unfinished, his own track.
- Identified portfolio gap that Grid Pulse fills: **nothing he owns runs live with a public track record** — no deployed service, no on-the-record predictions.

## Ideas researched and their verdicts (July 2026)

| Idea | Verdict |
|------|---------|
| **Grid Pulse (live accountable demand forecasting)** | **CHOSEN.** Offline academic studies exist; no open operational system with a public forecast record for Indian states. |
| Mumbai water clock (7 lakes levels + water-cut forecast) | Parked — charming weekend-scale civic project, data is scrapy daily PDFs; good second project someday. |
| Hinglish local-LLM leaderboard | Demoted — Hindi SLM benchmarking already exists (arXiv 2508.19831 benchmarks Gemma/Llama/Qwen-class on Hindi suites; MILU, SANSKRITI etc.). Only marginal code-switching novelty left. |
| AI photo culler | **REJECTED on values: Krish does not want AI touching his photographs. Do not re-suggest AI-on-his-photos projects.** |
| Rain-tax traffic angle | Declined earlier during jam-genome selection (rain kept only as a confounder column there). |

## Key research references

- NITI Aayog ICED hourly state load curves: https://iced.niti.gov.in/energy/electricity/distribution/national-level-consumption/load-curve
- Grid-India (ex-POSOCO) demand reports & PSP: https://posoco.in/en/reports/electricity-demand-pattern-analysis/ and https://posoco.in/en/demand-forecast/
- Kaggle historical POSOCO scrape (+ scraping notebook): https://www.kaggle.com/datasets/aryankhurana1701/state-wise-electricity-consumption-in-india
- Offline academic precedent (what we go beyond): data-driven XGBoost state demand models, IOP 2025: https://iopscience.iop.org/article/10.1088/2753-3751/adc7bc ; MIT thesis on Indian demand forecasting: https://dspace.mit.edu/bitstream/handle/1721.1/129084/1227274035-MIT.pdf
- Live per-state demand page to evaluate as scrape source: vidyutpravah.in (NOT yet verified — Phase 0 job)
- Weather: Open-Meteo (free, keyless, hourly forecast + archive)

## Decisions already made

1. Operational-accountability framing is the point: forecasts committed to git BEFORE the target day; wrong forecasts never deleted; baselines stay on the scoreboard forever.
2. Maharashtra first, expand to ~5 states once stable.
3. Phase 0 (data recon) precedes all code; pre-agreed pivot to daily-granularity forecasting if hourly feeds prove inaccessible.
4. Krish drives git himself — sessions prepare commits, he pushes; no Co-Authored-By lines.
5. This folder is the project home; suggested repo name: `grid-pulse`, public from day 1.
