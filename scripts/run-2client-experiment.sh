#!/bin/bash
# Run an experiment with 2 clients + traffic capture.
# Used to test RPCMode.Others relay behavior.
set -euo pipefail

EXPERIMENT="${1:?Usage: $0 <experiment-name>}"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
CAPTURES_DIR="$REPO_DIR/captures"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURE_BASE="$CAPTURES_DIR/${EXPERIMENT}-2client-${TIMESTAMP}"
PCAP_FILE="${CAPTURE_BASE}.pcap"
SERVER_LOG="${CAPTURE_BASE}-server.log"
CLIENT1_LOG="${CAPTURE_BASE}-client1.log"
CLIENT2_LOG="${CAPTURE_BASE}-client2.log"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

echo "=== 2-Client Experiment: $EXPERIMENT ==="

PIDS=()
PCAP_TMP="/tmp/experiment-2client-$$.pcap"
cleanup() {
    for pid in "${PIDS[@]}"; do
        sudo kill "$pid" 2>/dev/null || true
    done
    sleep 1
    for pid in "${PIDS[@]}"; do
        sudo kill -9 "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    if [ -f "$PCAP_TMP" ]; then
        sudo cp "$PCAP_TMP" "$PCAP_FILE" 2>/dev/null || true
        sudo chown "$(id -u):$(id -g)" "$PCAP_FILE" 2>/dev/null || true
        sudo rm -f "$PCAP_TMP" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Start tshark
sudo ip netns exec "$NS" tshark -i lo -f "udp port $PORT" -w "$PCAP_TMP" -F pcap -q &
PIDS+=($!)
sleep 1

# Start server
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment "$EXPERIMENT" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
SERVER_PID=${PIDS[-1]}

echo "Waiting for server..."
for i in $(seq 1 $TIMEOUT); do
    grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null && break
    kill -0 "$SERVER_PID" 2>/dev/null || { echo "Server died"; cat "$SERVER_LOG"; exit 1; }
    sleep 1
done
echo "Server ready."
sleep 0.5

# Start client 1
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment "$EXPERIMENT" \
    > "$CLIENT1_LOG" 2>&1 &
PIDS+=($!)
echo "Client 1 started."
sleep 2

# Start client 2
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment "$EXPERIMENT" \
    > "$CLIENT2_LOG" 2>&1 &
PIDS+=($!)
echo "Client 2 started."

# Wait for completion
DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "EXPERIMENT_DONE" "$CLIENT1_LOG" 2>/dev/null; then
        sleep 2
        break
    fi
    sleep 0.5
done

# Cleanup
for pid in "${PIDS[@]:1}"; do
    sudo kill "$pid" 2>/dev/null || true
done
sleep 1
sudo kill -INT "${PIDS[0]}" 2>/dev/null || true
sleep 2
PIDS=()

if [ -f "$PCAP_TMP" ]; then
    sudo cp "$PCAP_TMP" "$PCAP_FILE"
    sudo chown "$(id -u):$(id -g)" "$PCAP_FILE"
    sudo rm -f "$PCAP_TMP"
fi

echo ""
echo "=== Results ==="
echo "    Pcap:       $PCAP_FILE"
echo "    Server log: $SERVER_LOG"
echo "    Client 1:   $CLIENT1_LOG"
echo "    Client 2:   $CLIENT2_LOG"

PACKETS=$(tshark -r "$PCAP_FILE" 2>/dev/null | wc -l || echo "0")
echo "    Packets:    $PACKETS"

echo ""
echo "--- Server log (key lines) ---"
grep -E "\[Loader\]|\[Experiment\]|\[RPC\]|\[SecondRpc\]" "$SERVER_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Client 1 log (key lines) ---"
grep -E "\[Loader\]|\[Experiment\]|\[RPC\]" "$CLIENT1_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Client 2 log (key lines) ---"
grep -E "\[Loader\]|\[Experiment\]|\[RPC\]" "$CLIENT2_LOG" 2>/dev/null || echo "(none)"
