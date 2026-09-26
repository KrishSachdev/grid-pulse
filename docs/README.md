# Grid Pulse dashboard

A static, dependency-free dashboard for the collected Maharashtra demand + weather data. No build step, no CDN, no framework — three files: `index.html`, `style.css`, `app.js`.

## How it works

`app.js` fetches JSONL files directly from `raw.githubusercontent.com/KrishSachdev/grid-pulse/main/data/raw/...` in the visitor's browser (that endpoint sends permissive CORS headers, so this works from any static host). It pulls the last 14 IST calendar days of demand + weather, then draws everything as inline SVG built by hand with small helper functions in `app.js` — no charting library.

Because it fetches from GitHub at page-load time, the dashboard is always as fresh as the repo, wherever this folder is hosted (GitHub Pages, or opened locally).

## What's on it

- **Today vs. same day last week** — hourly demand line chart, two series.
- **Daily peak demand** — bar chart, last 14 days.
- **Collection health** — a strip of 14 day-cells, colored by hours captured out of 24 (green ≥22, yellow ≥12, red below).
- **Temperature vs. demand** — scatter plot over the same 14-day window.
- **Last updated** — timestamp of the most recent successful reading found.

## Honest failure mode

If GitHub is unreachable or the expected files are missing, the page shows a plain error message instead of silently rendering an empty or fake-looking chart.

## Hosting

Nothing to build. To publish on GitHub Pages: repo Settings → Pages → deploy from `main` branch, folder `/docs` (Pages can only serve the repo root or `/docs`). No server, no npm install, no secrets involved.
