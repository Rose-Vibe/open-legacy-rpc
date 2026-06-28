#!/bin/bash
# Investigate Unity's 16-bit timestamp expansion in 0x1b RPC messages.
#
# Usage:
#   ./scripts/run-timestamp-expansion.sh --unity-server    # Unity server + Unity client
#   ./scripts/run-timestamp-expansion.sh --python-server   # Python server + Unity client
#   ./scripts/run-timestamp-expansion.sh                   # defaults to --python-server
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="${PLAYER_OVERRIDE:-$REPO_DIR/UnityProject/Builds/Linux-patched/Player.x86_64}"
DLL_SRC="${DLL_OVERRIDE:-$REPO_DIR/experiments/Experiments.dll}"
NS="unitynet"
PORT=7777
TIMEOUT=120  # 2 minutes (phase 2 runs ~80 seconds)

MODE="${1:---python-server}"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/TimestampExpansion-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/TimestampExpansion-${TIMESTAMP}-client.log"
PCAP_FILE="$CAPTURES_DIR/TimestampExpansion-${TIMESTAMP}.pcap"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built. Run: cd experiments && bash build.sh"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found. Run: sudo bash netns-setup.sh"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== Timestamp Expansion Investigation ==="
echo "  Mode: $MODE"
echo "  Timeout: ${TIMEOUT}s"

PIDS=()
cleanup() {
    for pid in "${PIDS[@]}"; do
        sudo kill "$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${PIDS[@]}"; do
        sudo kill -9 "$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    done
    # Capture may still be running
    sudo pkill -f "tshark.*$PCAP_FILE" 2>/dev/null || true
}
trap cleanup EXIT

# Start packet capture
sudo ip netns exec "$NS" tshark -i lo -f 'udp port 7777' -w "$PCAP_FILE" \
    > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

if [ "$MODE" = "--unity-server" ]; then
    # Unity server
    sudo ip netns exec "$NS" "$PLAYER" \
        -batchmode -nographics -logFile - \
        -- --server --port "$PORT" --experiment TimestampExpansionExperiment \
        > "$SERVER_LOG" 2>&1 &
    PIDS+=($!)
    SERVER_PID=${PIDS[-1]}

    echo "Waiting for Unity server..."
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
    echo "Unity server running."
else
    # Python server
    sudo ip netns exec "$NS" python3 "$REPO_DIR/scripts/timestamp-expansion-server.py" \
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
fi

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
echo "--- Clock baseline ---"
grep -E "CLOCK BASELINE|Process\.|TickCount|realtimeSince|DateTime|Stopwatch" "$CLIENT_LOG" 2>/dev/null || echo "(no baseline lines)"
echo ""
echo "--- Received RPCs ---"
grep "RECV #" "$CLIENT_LOG" 2>/dev/null || echo "(no RECV lines)"
echo ""
echo "--- Derived values ---"
grep "DERIVED\|TIMESTAMP_BITS" "$CLIENT_LOG" 2>/dev/null || echo "(no derived lines)"
echo ""
echo "--- Server sends (if Unity server) ---"
grep "SERVER_SEND" "$SERVER_LOG" 2>/dev/null || echo "(n/a)"
echo ""

DELIVERED=$(grep -c "RECV #" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "=== DELIVERY: $DELIVERED RPCs received ==="
