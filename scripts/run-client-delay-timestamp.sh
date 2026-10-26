#!/bin/bash
# Test: does info.timestamp track client process uptime or Network.time?
# Client starts, waits CONNECT_DELAY seconds, then connects.
# If timestamp ≈ clientUptime: no server-side fix possible.
# If timestamp ≈ Network.time: the 16-bit mechanism adapts.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777
CONNECT_DELAY="${1:-60}"  # seconds client waits before connecting
TIMEOUT=180

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/ClientDelay-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/ClientDelay-${TIMESTAMP}-client.log"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== Client Delay Timestamp Experiment ==="
echo "  Connect delay: ${CONNECT_DELAY}s (client idles before connecting)"
echo "  Timeout: ${TIMEOUT}s after client starts"

PIDS=()
cleanup() {
    for pid in "${PIDS[@]}"; do
        sudo kill "$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${PIDS[@]}"; do
        sudo kill -9 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT

# Start server first
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment TimestampExpansionExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
SERVER_PID=${PIDS[-1]}

echo "Waiting for server to init..."
DEADLINE=$((SECONDS + 30))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "ERROR: Server died"
        cat "$SERVER_LOG"
        exit 1
    fi
    sleep 0.5
done
echo "Server running."

# Start client with connect delay
echo "Starting client with --connect-delay ${CONNECT_DELAY}..."
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment TimestampExpansionExperiment \
    --connect-delay "$CONNECT_DELAY" \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

echo "Waiting for experiment (timeout ${TIMEOUT}s)..."
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
    sleep 1
done

echo ""
echo "=== Results ==="
echo "    Server log: $SERVER_LOG"
echo "    Client log: $CLIENT_LOG"
echo ""
echo "--- Client clock baseline ---"
grep -E "CLOCK BASELINE|CLOCKS|realtimeSince|Network\.time|Connect delay|Waiting\.\.\." "$CLIENT_LOG" 2>/dev/null | head -10 || echo "(no baseline)"
echo ""
echo "--- Client received RPCs ---"
grep "\[RPC\]" "$CLIENT_LOG" 2>/dev/null | head -20 || echo "(no RPCs)"
echo ""
echo "--- Server sends ---"
grep "PHASE\|SEND\|Player connected" "$SERVER_LOG" 2>/dev/null | head -15 || echo "(no sends)"
echo ""

DELIVERED=$(grep -c "\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "=== DELIVERY: $DELIVERED RPCs received ==="
echo ""
echo "=== KEY QUESTION: Does timestamp ≈ clientUptime (~${CONNECT_DELAY}s) or ≈ Network.time? ==="
