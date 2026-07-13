#!/bin/bash
# Runs the method_tag collision repro (docs/plans/method-tag-collision-repro.md),
# scenarios S1-S7, against the real headless Unity Linux player.
#
# Usage:
#   scripts/run-tag-collision.sh                # all scenarios 1-7, once each
#   scripts/run-tag-collision.sh 2               # just scenario 2
#   scripts/run-tag-collision.sh 2 3             # scenarios 2 and 3
#   REPEAT=3 scripts/run-tag-collision.sh 2 3    # scenarios 2 and 3, 3x each
#
# Launches a fresh Unity client process per scenario (and per repeat) so no
# run's connection state leaks into the next.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
DRIVER="$REPO_DIR/scripts/tag-collision-server.py"
NS="unitynet"
PORT=7777
TIMEOUT=30
REPEAT="${REPEAT:-1}"
LABEL="TagCollision"

if [ "$#" -eq 0 ]; then
    SCENARIOS="1 2 3 4 5 6 7"
else
    SCENARIOS="$*"
fi

CAPTURES_DIR="$REPO_DIR/captures"
mkdir -p "$CAPTURES_DIR"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "=== $LABEL (repeat=$REPEAT) ==="

for N in $SCENARIOS; do
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    PCAP="$CAPTURES_DIR/${LABEL}-scenario${N}-${TIMESTAMP}.pcap"
    SERVER_LOG="$CAPTURES_DIR/${LABEL}-scenario${N}-${TIMESTAMP}-server.log"
    CLIENT_LOG="$CAPTURES_DIR/${LABEL}-scenario${N}-${TIMESTAMP}-client.log"

    echo ""
    echo "--- Scenario $N ---"

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

    PCAP_TMP="/tmp/tag-collision-scenario${N}-capture.pcap"
    sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
    PIDS+=($!)
    sleep 1

    sudo ip netns exec "$NS" python3 "$DRIVER" --scenario "$N" --port "$PORT" \
        --repeat "$REPEAT" > "$SERVER_LOG" 2>&1 &
    PIDS+=($!)
    sleep 2

    sudo ip netns exec "$NS" "$PLAYER" \
        -batchmode -nographics -logFile - \
        -- --client --port "$PORT" --experiment TagCollisionExperiment \
        > "$CLIENT_LOG" 2>&1 &
    PIDS+=($!)

    DEADLINE=$((SECONDS + TIMEOUT))
    while [ $SECONDS -lt $DEADLINE ]; do
        if grep -q "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null; then
            sleep 2
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
    echo "Batch-index registrations and warnings from server driver:"
    grep -iE "batch_index|precondition|re-sending first-use|warning" "$SERVER_LOG" 2>/dev/null || echo "  (none)"
done
