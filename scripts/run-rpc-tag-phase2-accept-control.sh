#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
PCAP="$CAPTURES_DIR/RpcTagPhase2AcceptControl-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/RpcTagPhase2AcceptControl-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/RpcTagPhase2AcceptControl-${TIMESTAMP}-client.log"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments" "$CAPTURES_DIR"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "=== Phase 2 ACCEPT CONTROL: correct tag on a STATIC (Loader) RPC method ==="

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

PCAP_TMP="/tmp/rpc-tag-phase2-accept-control-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

sudo ip netns exec "$NS" python3 "$REPO_DIR/scripts/rpc-tag-phase2-accept-control.py" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 2

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment WrongIndexExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "Server stopped" "$SERVER_LOG" 2>/dev/null; then
        sleep 2
        break
    fi
    if ! kill -0 "$CLIENT_PID" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

echo ""
echo "--- Server Log ---"
grep -v "^$" "$SERVER_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Client Results ---"
grep -E "\[Experiment\]|\[RPC\]|Internal RPC error" "$CLIENT_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Summary ---"
echo "Expected: RPC_Beta(555) dispatched cleanly, no error -- correct tag should never be rejected."

sudo cp "$PCAP_TMP" "$PCAP" 2>/dev/null && sudo chmod 644 "$PCAP"
echo ""
echo "Pcap: $PCAP"
echo "Server log: $SERVER_LOG"
echo "Client log: $CLIENT_LOG"
