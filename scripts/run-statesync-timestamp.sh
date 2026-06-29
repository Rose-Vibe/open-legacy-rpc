#!/bin/bash
# State sync timestamp experiment: Unity server + Unity client with staggered start.
# Server starts first, we wait DELAY seconds (default 70s), then client connects.
# Tests whether bytes 1-8 of state sync messages are a u64 timestamp (like RPCs).
# If they are, byte 6 will overflow past 0x00 when server uptime > 65535ms.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="${PLAYER_OVERRIDE:-$REPO_DIR/UnityProject/Builds/Linux-patched/Player.x86_64}"
DLL_SRC="${DLL_OVERRIDE:-$REPO_DIR/experiments/Experiments.dll}"
NS="unitynet"
PORT=7777
DELAY="${1:-70}"
TIMEOUT=120

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/StateSyncTs-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/StateSyncTs-${TIMESTAMP}-client.log"
PCAP_FILE="$CAPTURES_DIR/StateSyncTs-${TIMESTAMP}.pcap"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== State Sync Timestamp Experiment ==="
echo "  Delay: ${DELAY}s between server and client start"
echo "  Timeout: ${TIMEOUT}s after client starts"

PIDS=()
TSHARK_PID=""
cleanup() {
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
sudo ip netns exec "$NS" dumpcap -i lo -f 'udp port 7777' -w "$PCAP_FILE" \
    2>/dev/null &
TSHARK_PID=$!
PIDS+=($TSHARK_PID)
sleep 2

# Start Unity server
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment StateSyncTimestampExperiment \
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

# Wait the stagger delay — server accumulates uptime
sleep "$DELAY"

echo "Starting client now (server has been running ~${DELAY}s)..."

# Start Unity client
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment StateSyncTimestampExperiment \
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
grep -E "CLOCK BASELINE|realtimeSince|Network\.time" "$SERVER_LOG" 2>/dev/null | head -10 || echo "(no baseline)"
echo ""
echo "--- Client clock baseline ---"
grep -E "CLOCK BASELINE|realtimeSince|Network\.time" "$CLIENT_LOG" 2>/dev/null | head -10 || echo "(no baseline)"
echo ""
echo "--- Client received state syncs ---"
grep "RECV" "$CLIENT_LOG" 2>/dev/null | head -30 || echo "(no receives)"
echo ""

RECEIVED=$(grep -c "RECV" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "=== RECEIVED: $RECEIVED state sync messages ==="
echo ""
echo "Next: decode the pcap and check bytes 1-8 of 0x1B state sync messages."
echo "  python3 tools/decode_pcap.py '$PCAP_FILE' --config '{\"serverPort\": $PORT}'"
