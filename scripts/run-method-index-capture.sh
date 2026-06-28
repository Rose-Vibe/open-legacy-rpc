#!/bin/bash
# Capture what method_index Unity assigns in subsequent-use RPCs.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/MethodIndexCapture-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/MethodIndexCapture-${TIMESTAMP}-client.log"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments" "$CAPTURES_DIR"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "=== Method Index Capture ==="

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

# Run Unity as SERVER (it sends RPCs to itself via client)
# Actually: client sends RPCs to Python server, Python captures raw bytes
sudo ip netns exec "$NS" python3 "$REPO_DIR/scripts/method-index-capture-server.py" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 2

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment MethodIndexCaptureExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "Done\." "$SERVER_LOG" 2>/dev/null; then
        sleep 1
        break
    fi
    if grep -q "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null; then
        sleep 2
        break
    fi
    sleep 0.5
done

echo ""
echo "--- Python capture server ---"
cat "$SERVER_LOG"
echo ""
echo "--- Unity client ---"
grep -E "\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(no matching lines)"
