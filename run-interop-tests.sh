#!/bin/bash
# Run end-to-end interop tests: Python ↔ Unity in both directions.
#
# Test 1: Unity server (InteropExperiment) + Python client
# Test 2: Python server + Unity client (ClientInteropExperiment)
#
# Requires: network namespace "unitynet", Unity player built, Experiments.dll built.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777

# Pre-flight
[ -f "$PLAYER" ] || { echo "ERROR: Player not built"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

# Deploy DLL
PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

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

RESULT=0

# ──────────────────────────────────────────────
# Test 1: Unity server + Python client
# ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo " Test 1: Unity server + Python client"
echo "═══════════════════════════════════════════"

PIDS=()
trap cleanup EXIT

# Start Unity server
SERVER_LOG="/tmp/interop-unity-server-$$.log"
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment InteropExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
UNITY_SERVER_PID=${PIDS[-1]}

# Wait for server ready
echo "Waiting for Unity server..."
for i in $(seq 1 30); do
    if grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null; then
        echo "Unity server ready."
        break
    fi
    if ! kill -0 "$UNITY_SERVER_PID" 2>/dev/null; then
        echo "ERROR: Unity server died."
        cat "$SERVER_LOG"
        RESULT=1
        break
    fi
    sleep 1
done

if [ "$RESULT" = "0" ] && grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null; then
    sleep 1
    # Run Python client
    echo "Running Python client..."
    if sudo ip netns exec "$NS" python3 "$REPO_DIR/tests/interop_python_client.py"; then
        echo "✓ Test 1 PASSED"
    else
        echo "✗ Test 1 FAILED"
        RESULT=1
    fi
fi

# Cleanup test 1
cleanup
PIDS=()
sleep 2

# ──────────────────────────────────────────────
# Test 2: Python server + Unity client
# ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════"
echo " Test 2: Python server + Unity client"
echo "═══════════════════════════════════════════"

trap cleanup EXIT

# Start Python server
echo "Starting Python server..."
sudo ip netns exec "$NS" python3 "$REPO_DIR/tests/interop_python_server.py" &
PIDS+=($!)
PYTHON_SERVER_PID=${PIDS[-1]}
sleep 2

# Start Unity client
CLIENT_LOG="/tmp/interop-unity-client-$$.log"
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment ClientInteropExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)

# Wait for Python server to finish (it exits after receiving expected RPCs or timeout)
echo "Waiting for Python server to finish..."
wait "$PYTHON_SERVER_PID" 2>/dev/null
PYTHON_EXIT=$?
if [ "$PYTHON_EXIT" = "0" ]; then
    echo "✓ Test 2 PASSED"
else
    echo "✗ Test 2 FAILED (exit code $PYTHON_EXIT)"
    echo "--- Unity client log ---"
    grep -E "\[Loader\]|\[Experiment\]|\[RPC\]|Error|Exception" "$CLIENT_LOG" 2>/dev/null | head -20
    RESULT=1
fi

# Cleanup test 2
cleanup
PIDS=()

echo ""
echo "═══════════════════════════════════════════"
if [ "$RESULT" = "0" ]; then
    echo " ALL INTEROP TESTS PASSED"
else
    echo " SOME INTEROP TESTS FAILED"
fi
echo "═══════════════════════════════════════════"

exit $RESULT
