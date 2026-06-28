#!/bin/bash
# Test whether the 16-bit "zeros" field (bits 88-103) in RPCs is a timestamp.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="${PLAYER_OVERRIDE:-$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64}"
DLL_SRC="${DLL_OVERRIDE:-$REPO_DIR/experiments/Experiments.dll}"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/TimestampField-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/TimestampField-${TIMESTAMP}-client.log"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== Timestamp Field Test ==="

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

sudo ip netns exec "$NS" python3 "$REPO_DIR/scripts/timestamp-field-server.py" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
SERVER_PID=${PIDS[-1]}

echo "Waiting for Python server..."
sleep 2

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ERROR: Python server died"
    cat "$SERVER_LOG"
    exit 1
fi
echo "Python server running."

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment TimestampFieldExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

echo "Waiting for experiment..."
DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null; then
        sleep 2
        break
    fi
    if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
        echo "Client exited early."
        break
    fi
    sleep 0.5
done

echo ""
echo "=== Results ==="
echo "    Server log: $SERVER_LOG"
echo "    Client log: $CLIENT_LOG"
echo ""
echo "--- Python server log ---"
cat "$SERVER_LOG"
echo ""
echo "--- Unity client (key lines) ---"
grep -E "\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(no matching lines)"
echo ""

DELIVERED=$(grep -c "\[RPC\] RPC_Int" "$CLIENT_LOG" 2>/dev/null || echo "0")
TOTAL=9  # updated if TEST_CASES changes
echo "=== DELIVERY: $DELIVERED / $TOTAL RPCs received ==="
echo ""
echo "--- Timestamp details ---"
grep "RECV #" "$CLIENT_LOG" 2>/dev/null || echo "(no RECV lines)"
