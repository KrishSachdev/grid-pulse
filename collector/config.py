"""Grid Pulse collector configuration.

Single source of truth for what we collect and where it lands. Start with
Maharashtra only (Phase 1); add states here once the MH pipeline is stable.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_HISTORY = REPO_ROOT / "data" / "history"
DEMAND_DIR = DATA_RAW / "demand"
WEATHER_DIR = DATA_RAW / "weather"

# Identify ourselves politely to public government portals.
USER_AGENT = "grid-pulse/0.1 (+https://github.com/KrishSachdev)"

# Sampling grid, in minutes. The forecast target is *hourly* demand, so we store one
# reading per hourly slot per state (a snapshot near the top of the hour — the standard
# representation used by hourly demand models). The Actions cron runs more often than
# this (every 15 min) and the slot guard keeps only the first success per slot, so we
# stay robust to GitHub skipping cron slots without duplicating data.
# To capture intra-hour shape later, drop DEMAND_SLOT_MINUTES to 15 (one-line change).
DEMAND_SLOT_MINUTES = 60
WEATHER_SLOT_MINUTES = 60

# --- Demand: vidyutpravah live per-state "Demand Met" page -------------------
# Per-state page is server-rendered (values are in the HTML, not an XHR).
VIDYUTPRAVAH_URL = "https://vidyutpravah.in/state-data/{slug}"

# States to collect. `slug` is the vidyutpravah URL slug.
STATES = {
    "maharashtra": {"name": "Maharashtra"},
    # Add once MH is stable (slugs verified on vidyutpravah.in):
    # "delhi": {"name": "Delhi"},
    # "gujarat": {"name": "Gujarat"},
    # "tamil-nadu": {"name": "Tamil Nadu"},
    # "uttar-pradesh": {"name": "Uttar Pradesh"},
}

# --- Weather: Open-Meteo (free, keyless, IST-aware) --------------------------
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"

# Population/load-weighted city points per state. Weights are provisional (rough
# metro + industrial load share) and sum to 1.0 per state; tune once we can
# regress demand on per-city weather. For MH: Mumbai, Pune, Nagpur, Nashik.
WEATHER_POINTS = {
    "maharashtra": [
        {"city": "Mumbai", "lat": 19.0760, "lon": 72.8777, "weight": 0.45},
        {"city": "Pune",   "lat": 18.5204, "lon": 73.8567, "weight": 0.28},
        {"city": "Nagpur", "lat": 21.1458, "lon": 79.0882, "weight": 0.15},
        {"city": "Nashik", "lat": 19.9975, "lon": 73.7898, "weight": 0.12},
    ],
}
