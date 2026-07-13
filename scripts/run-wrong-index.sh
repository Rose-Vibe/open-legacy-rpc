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
PCAP="$CAPTURES_DIR/WrongIndex-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/WrongIndex-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/WrongIndex-${TIMESTAMP}-client.log"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments" "$CAPTURES_DIR"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "=== Wrong Index Experiment ==="
echo "Tests whether Unity learns method_index from traffic or rejects wrong indices"

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

# Start pcap capture
PCAP_TMP="/tmp/wrong-index-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

# Start Python server (NOT Unity — we're crafting custom packets)
sudo ip netns exec "$NS" python3 "$REPO_DIR/scripts/wrong-index-server.py" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 2

# Start Unity client
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment WrongIndexExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)

DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -q "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null; then
        sleep 3
        break
    fi
    sleep 0.5
done

echo ""
echo "--- Server Log ---"
grep -v "^$" "$SERVER_LOG" 2>/dev/null | tail -30 || echo "(none)"
echo ""
echo "--- Client Results ---"
grep -E "\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Summary ---"
RPC_COUNT=$(grep -c "\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "Total [RPC] calls received by Unity client: $RPC_COUNT"
echo ""
echo "Expected if Unity LEARNS from traffic:  6 RPCs"
echo "  Phase 1: RPC_Int(100)    — first-use, always works"
echo "  Phase 2: RPC_Int(101)    — subsequent-use, fake index 0x30"
echo "  Phase 3: RPC_Int(102)    — subsequent-use, same fake index"
echo "  Phase 4: RPC_Float(3.14) — first-use, always works"
echo "  Phase 5: RPC_Float(2.72) — subsequent-use, fake index 0x08"
echo "  Phase 7: RPC_String(alive) — first-use after orphan"
echo ""
echo "Expected if Unity PRE-COMPUTES indices: 3 RPCs"
echo "  Phase 1,4,7 only (first-use works, all subsequent-use dropped)"
echo ""

sudo cp "$PCAP_TMP" "$PCAP" 2>/dev/null && sudo chmod 644 "$PCAP"
echo "Pcap: $PCAP"
echo "Server log: $SERVER_LOG"
echo "Client log: $CLIENT_LOG"
