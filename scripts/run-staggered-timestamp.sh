#!/bin/bash
# Thread A: Unity server + Unity client with staggered start.
# Server starts first, we wait DELAY seconds, then client connects.
# This tests whether Unity handles clock skew natively.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="${PLAYER_OVERRIDE:-$REPO_DIR/UnityProject/Builds/Linux-patched/Player.x86_64}"
DLL_SRC="${DLL_OVERRIDE:-$REPO_DIR/experiments/Experiments.dll}"
NS="unitynet"
PORT=7777
DELAY="${1:-70}"  # seconds to wait between server and client start
TIMEOUT=120

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/StaggeredTimestamp-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/StaggeredTimestamp-${TIMESTAMP}-client.log"
PCAP_FILE="$CAPTURES_DIR/StaggeredTimestamp-${TIMESTAMP}.pcap"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== Staggered Timestamp Experiment ==="
echo "  Delay: ${DELAY}s between server and client start"
echo "  Timeout: ${TIMEOUT}s after client starts"

PIDS=()
TSHARK_PID=""
cleanup() {
    # Stop tshark gracefully first so it flushes the pcap
    if [ -n "$TSHARK_PID" ]; then
        sudo kill -INT "$TSHARK_PID" 2>/dev/null || true
        sleep 2
    fi
    for pid in "${PIDS[@]}"; do
        sudo kill "$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${PIDS[@]}"; do
        sudo kill -9 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT

# Start packet capture
sudo ip netns exec "$NS" tshark -i lo -f 'udp port 7777' -w "$PCAP_FILE" \
    2>/dev/null &
TSHARK_PID=$!
PIDS+=($TSHARK_PID)
sleep 2

# Start Unity server
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment TimestampExpansionExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
SERVER_PID=${PIDS[-1]}

echo "Waiting for Unity server to init..."
DEADLINE=$((SECONDS + 30))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "ERROR: Unity server died"
        cat "$SERVER_LOG"
        exit 1
    fi
    sleep 0.5
done
echo "Server running. Waiting ${DELAY}s before starting client..."

# Wait the stagger delay
sleep "$DELAY"

echo "Starting client now (server has been running ~${DELAY}s)..."

# Start Unity client
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment TimestampExpansionExperiment \
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
    sleep 0.5
done

echo ""
echo "=== Results ==="
echo "    Server log: $SERVER_LOG"
echo "    Client log: $CLIENT_LOG"
echo "    PCAP: $PCAP_FILE"
echo ""
echo "--- Server clock baseline ---"
grep -E "CLOCK BASELINE|Process\.|TickCount|realtimeSince|DateTime|Network\.time" "$SERVER_LOG" 2>/dev/null || echo "(no baseline)"
echo ""
echo "--- Client clock baseline ---"
grep -E "CLOCK BASELINE|Process\.|TickCount|realtimeSince|DateTime|Network\.time" "$CLIENT_LOG" 2>/dev/null || echo "(no baseline)"
echo ""
echo "--- Server sends ---"
grep "PHASE\|SEND\|Player connected" "$SERVER_LOG" 2>/dev/null | head -20 || echo "(no sends)"
echo ""
echo "--- Client received RPCs ---"
grep "\[RPC\]\|RECV\|timestamp\|Network\.time" "$CLIENT_LOG" 2>/dev/null | head -30 || echo "(no RPCs)"
echo ""
echo "--- Periodic clock ticks (client) ---"
grep "Tick #" "$CLIENT_LOG" 2>/dev/null | head -20 || echo "(no ticks)"
echo ""

DELIVERED=$(grep -c "\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "=== DELIVERY: $DELIVERED RPCs received ==="
