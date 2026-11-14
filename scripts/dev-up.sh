#!/usr/bin/env bash
# Start the full stack on localhost with synthetic data and no broker:
# hub (all features, DONKI replay), link simulator (demo config), ground receiver,
# and sim-1 replaying data/replay/l0-synthetic.jsonl over HTTP.
# Usage: scripts/dev-up.sh [--no-sim]   (stop with Ctrl-C)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] && . .venv/bin/activate

LOG=var/dev-up
mkdir -p "$LOG"
PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

export HUB_DB="$LOG/hub.db"
export HUB_MQTT_HOST=""            # no broker: the subscriber stays off
export DONKI_MODE=replay           # committed DONKI snapshot, no network
export HUB_HTTP_HOST=127.0.0.1
export HUB_LINKSIM_URL=http://127.0.0.1:8200
export HUB_LINK_CONFIG=linksim/link.demo.json
rm -f "$LOG"/hub.db* "$LOG"/ground.db* "$LOG"/state.json

python -m hub >"$LOG/hub.log" 2>&1 & PIDS+=($!)
python -m linksim --config linksim/link.demo.json --hub http://127.0.0.1:8000 \
  --ground http://127.0.0.1:8100 --state "$LOG/state.json" >"$LOG/linksim.log" 2>&1 & PIDS+=($!)
python -m receiver --db "$LOG/ground.db" --host 127.0.0.1 --port 8100 >"$LOG/receiver.log" 2>&1 & PIDS+=($!)

for _ in $(seq 1 40); do
  curl -fsS http://127.0.0.1:8000/api/status >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS http://127.0.0.1:8000/api/status >/dev/null || { echo "hub did not start; see $LOG/hub.log"; exit 1; }
echo "hub http://127.0.0.1:8000  linksim :8200  receiver :8100  logs in $LOG/"

if [ "${1:-}" != "--no-sim" ]; then
  python -m hub.sim --file data/replay/l0-synthetic.jsonl --http http://127.0.0.1:8000 \
    --speed 60 --backdate --state "$LOG/sim.boot" | tee "$LOG/sim.log"
fi
echo "stack is up; Ctrl-C to stop"
wait
