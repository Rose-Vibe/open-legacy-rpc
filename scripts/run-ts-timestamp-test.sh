#!/bin/bash
# Test TS server → Unity client timestamps with a time gap.
# Server runs for DELAY seconds before client connects.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="${PLAYER_OVERRIDE:-$REPO_DIR/UnityProject/Builds/Linux-patched/Player.x86_64}"
DLL_SRC="${DLL_OVERRIDE:-$REPO_DIR/experiments/Experiments.dll}"
NS="unitynet"
PORT=7777
DELAY="${1:-10}"
TIMEOUT=60

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
SERVER_LOG="$CAPTURES_DIR/TsTimestamp-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/TsTimestamp-${TIMESTAMP}-client.log"

[ -f "$PLAYER" ] || { echo "ERROR: Player not built"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built"; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found"; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$CAPTURES_DIR"

TSX_CLI="$(find "$REPO_DIR/ts/node_modules" -name 'cli.mjs' -path '*/tsx/*' | head -1)"
[ -f "$TSX_CLI" ] || { echo "ERROR: tsx cli.mjs not found"; exit 1; }

echo "=== TS Server Timestamp Test ==="
echo "  Delay: ${DELAY}s before client start"

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

# Start TS server
NODE="$(which node)"
sudo ip netns exec "$NS" "$NODE" "$TSX_CLI" "$REPO_DIR/scripts/ts-timestamp-server.ts" \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
SERVER_PID=${PIDS[-1]}

echo "Waiting for TS server..."
sleep 3

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ERROR: TS server died"
    cat "$SERVER_LOG"
    exit 1
fi
echo "TS server running. Waiting ${DELAY}s before starting client..."
sleep "$DELAY"

# Start Unity client
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment TimestampExpansionExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

echo "Client started, waiting for RPCs (timeout ${TIMEOUT}s)..."
DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    if grep -c "\[RPC\].*RPC_Int(11" "$CLIENT_LOG" 2>/dev/null | grep -q '[1-9]'; then
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
echo "Server log: $SERVER_LOG"
echo "Client log: $CLIENT_LOG"
echo ""
echo "--- Server sends ---"
grep '\[TS Server\]' "$SERVER_LOG" 2>/dev/null | head -20 || echo "(no server log)"
echo ""
echo "--- Client received RPCs ---"
grep -E '\[RPC\]|CLOCK|connected' "$CLIENT_LOG" 2>/dev/null | head -30 || echo "(no RPCs)"
echo ""

DELIVERED=$(grep -c '\[RPC\]' "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "=== DELIVERY: $DELIVERED RPCs received ==="
