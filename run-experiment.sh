#!/bin/bash
# Run an experiment with traffic capture.
#
# Usage: ./run-experiment.sh <experiment-class-name> [extra-args...]
#
# Requires:
#   - Network namespace "unitynet" (sudo bash netns-setup.sh)
#   - tshark installed (sudo apt install -y tshark)
#   - Unity player built (UnityProject/Builds/Linux/Player.x86_64)
#   - Experiments DLL built (bash experiments/build.sh)

set -euo pipefail

EXPERIMENT="${1:?Usage: $0 <experiment-name> [extra-args...]}"
shift
EXTRA_ARGS=("$@")

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAYER="${PLAYER_OVERRIDE:-$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64}"
DLL_SRC="${DLL_OVERRIDE:-$REPO_DIR/experiments/Experiments.dll}"
CAPTURES_DIR="$REPO_DIR/captures"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURE_BASE="$CAPTURES_DIR/${EXPERIMENT}-${TIMESTAMP}"
PCAP_FILE="${CAPTURE_BASE}.pcap"
SERVER_LOG="${CAPTURE_BASE}-server.log"
CLIENT_LOG="${CAPTURE_BASE}-client.log"

# Pre-flight checks
for cmd in tshark; do
    command -v "$cmd" >/dev/null || { echo "ERROR: $cmd not found. Install it first."; exit 1; }
done
[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built. Run: bash experiments/build.sh"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found. Run: sudo bash netns-setup.sh"; exit 1; }

# Deploy DLL next to the player
PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

mkdir -p "$CAPTURES_DIR"

echo "=== Experiment: $EXPERIMENT ==="
echo "    Capture: $PCAP_FILE"
echo ""

# Cleanup on exit
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
    # Copy pcap from tmp to captures dir
    if [ -f "$PCAP_TMP" ]; then
        sudo cp "$PCAP_TMP" "$PCAP_FILE" 2>/dev/null || cp "$PCAP_TMP" "$PCAP_FILE" 2>/dev/null || true
        sudo chown "$(id -u):$(id -g)" "$PCAP_FILE" 2>/dev/null || true
        sudo rm -f "$PCAP_TMP" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Start tshark inside the namespace to capture on lo
# Write to /tmp first (root-writable), then copy out on cleanup
PCAP_TMP="/tmp/experiment-capture-$$.pcap"
sudo ip netns exec "$NS" tshark -i lo -f "udp port $PORT" -w "$PCAP_TMP" -F pcap -q &
PIDS+=($!)
sleep 1

# Start server inside the namespace
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment "$EXPERIMENT" "${EXTRA_ARGS[@]}" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
SERVER_PID=${PIDS[-1]}

# Wait for server to be ready
echo "Waiting for server..."
for i in $(seq 1 $TIMEOUT); do
    if grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null; then
        echo "Server ready."
        break
    fi
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "ERROR: Server process died."
        cat "$SERVER_LOG"
        exit 1
    fi
    sleep 1
done

if ! grep -q "OnServerInitialized" "$SERVER_LOG" 2>/dev/null; then
    echo "ERROR: Server did not initialize within ${TIMEOUT}s"
    cat "$SERVER_LOG"
    exit 1
fi

# Brief pause to let server fully stabilize
sleep 0.5

# Start client inside the namespace
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment "$EXPERIMENT" "${EXTRA_ARGS[@]}" \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

# Wait for experiment completion or timeout
echo "Waiting for experiment to complete..."
DEADLINE=$((SECONDS + TIMEOUT))
DONE=false
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "EXPERIMENT_DONE" "$SERVER_LOG" 2>/dev/null && \
       grep -q "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null; then
        DONE=true
        break
    fi
    # Also check if either side alone is done (for server-only or client-only experiments)
    if grep -q "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null; then
        # Give server a moment to finish too
        sleep 1
        DONE=true
        break
    fi
    if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
        echo "Client process exited."
        sleep 1
        DONE=true
        break
    fi
    sleep 0.5
done

# Stop processes and collect pcap
# Kill server and client first, then tshark (so it captures any final traffic)
for pid in "$CLIENT_PID" "$SERVER_PID"; do
    sudo kill "$pid" 2>/dev/null || true
done
sleep 1

# Stop tshark gracefully (SIGINT to flush)
TSHARK_PID="${PIDS[0]}"
sudo kill -INT "$TSHARK_PID" 2>/dev/null || true
sleep 2

# Clear the trap so cleanup doesn't double-kill
PIDS=()

# Copy pcap from tmp
if [ -f "$PCAP_TMP" ]; then
    sudo cp "$PCAP_TMP" "$PCAP_FILE"
    sudo chown "$(id -u):$(id -g)" "$PCAP_FILE"
    sudo rm -f "$PCAP_TMP"
fi

echo ""
echo "=== Results ==="
echo "    Pcap:       $PCAP_FILE"
echo "    Server log: $SERVER_LOG"
echo "    Client log: $CLIENT_LOG"

if [ "$DONE" = true ]; then
    echo "    Status:     COMPLETED"
else
    echo "    Status:     TIMEOUT (experiment may be incomplete)"
fi

# Show packet count
PACKETS=$(tshark -r "$PCAP_FILE" 2>/dev/null | wc -l || echo "0")
echo "    Packets:    $PACKETS"

echo ""
echo "--- Server log (key lines) ---"
grep -E "\[Loader\]|\[Experiment\]|\[RPC\]" "$SERVER_LOG" 2>/dev/null || echo "(no matching lines)"
echo ""
echo "--- Client log (key lines) ---"
grep -E "\[Loader\]|\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(no matching lines)"
