#!/bin/bash
# Runs the static-index-table validation sweep (scripts/index-sweep-server.py),
# a follow-up to the method_tag collision repro's S2 anomaly
# (docs/plans/method-tag-collision-repro.md).
#
# Usage:
#   scripts/run-index-sweep.sh
#
# Launches a single Unity client process against the sweep driver, which
# exercises first-use + computed-static-index subsequent-use for every
# Loader RPC method in one connection, plus one negative control.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
DRIVER="$REPO_DIR/scripts/index-sweep-server.py"
NS="unitynet"
PORT=7777
# The sweep drives 13 methods x 2 sends plus a negative control and settle
# time from the SERVER side; the client's TagCollisionExperiment.cs logs
# EXPERIMENT_DONE at a fixed tick count that has nothing to do with the
# sweep's actual duration, so we wait on the server log's own completion
# line ("Server stopped.") instead of the client's marker.
TIMEOUT=120
LABEL="IndexSweep"

CAPTURES_DIR="$REPO_DIR/captures"
mkdir -p "$CAPTURES_DIR"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
PCAP="$CAPTURES_DIR/${LABEL}-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/${LABEL}-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/${LABEL}-${TIMESTAMP}-client.log"

echo "=== $LABEL ==="

PIDS=()
cleanup() {
    for pid in "${PIDS[@]}"; do
        sudo kill "$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${PIDS[@]}"; do
        sudo kill -9 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT

PCAP_TMP="/tmp/index-sweep-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

sudo ip netns exec "$NS" python3 "$DRIVER" --port "$PORT" > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 2

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment TagCollisionExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)

DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "Server stopped." "$SERVER_LOG" 2>/dev/null; then
        sleep 1
        break
    fi
    sleep 0.5
done

cleanup
trap - EXIT

sudo cp "$PCAP_TMP" "$PCAP" 2>/dev/null && sudo chmod 644 "$PCAP"
sudo rm -f "$PCAP_TMP"

echo "Server log: $SERVER_LOG"
echo "Client log: $CLIENT_LOG"
echo "Pcap: $PCAP"
echo ""
echo "[RPC] lines received by client:"
grep -E "\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "  (none)"
echo ""
echo "Internal RPC errors (explicit rejection, distinct from silence):"
grep -i "internal rpc error" "$CLIENT_LOG" 2>/dev/null || echo "  (none)"
echo ""
echo "Batch-index registrations from server driver:"
grep -iE "batch_index" "$SERVER_LOG" 2>/dev/null || echo "  (none)"
