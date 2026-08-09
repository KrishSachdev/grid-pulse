#!/bin/sh
# Grid Pulse — NAS entry point (DSM Task Scheduler runs this every 15 min).
#
# Mirrors the hwradar pattern: a node-local clone at ~/gridpulse/grid-pulse,
# deliberately NOT the Synology Drive-synced copy — Drive syncing a live .git
# between PC and NAS would corrupt the repo.
#
# DSM → Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script
#   User: KrishSachdev   Schedule: daily, repeat every 15 minutes
#   Command:  sh /var/services/homes/KrishSachdev/gridpulse/grid-pulse/collector/run_nas.sh
set -e

REPO="$HOME/gridpulse/grid-pulse"
cd "$REPO"

# DSM's scheduler runs with a minimal PATH; find python3 wherever DSM put it.
PY="$(command -v python3 || echo /usr/local/bin/python3)"

exec "$PY" -m collector.run_and_push >> "$HOME/gridpulse/collect.log" 2>&1
