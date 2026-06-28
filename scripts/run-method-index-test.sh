#!/bin/bash
# Run the method_index assignment experiment.
# Python server sends RPCs with various method_index values to test
# whether Unity computes the index or caches it from the sender.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/MethodIndex-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/MethodIndex-${TIMESTAMP}-client.log"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== Method Index Experiment ==="

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

# Both server and client run inside the network namespace
sudo ip netns exec "$NS" python3 "$REPO_DIR/scripts/method-index-server.py" \
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
    -- --client --port "$PORT" --experiment MethodIndexExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

echo "Waiting for experiment..."
DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "Done\." "$SERVER_LOG" 2>/dev/null; then
        sleep 2
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Server exited."
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
echo "--- Unity client RPC receipts ---"
grep -E "\[RPC\]|\[Experiment\]|error|Error" "$CLIENT_LOG" 2>/dev/null || echo "(no matching lines)"
echo ""

DELIVERED=$(grep -c "\[RPC\] RPC_Int" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "=== DELIVERY SUMMARY ==="
echo "Test A (first-use + subsequent 0x54): expect RPC_Int(100) and RPC_Int(101)"
echo "Test B (first-use + subsequent 0x42): expect RPC_Int(200), maybe RPC_Int(201)"
echo "Test C (first-use + subsequent 0x00): expect RPC_Int(300), maybe RPC_Int(301)"
echo "Test D (subsequent 0x54, no first-use): maybe RPC_Int(400)"
echo "Test E (first-use + 2x subsequent 0x20): expect RPC_Int(500), maybe RPC_Int(501,502)"
echo ""
echo "Total RPCs received: $DELIVERED"
