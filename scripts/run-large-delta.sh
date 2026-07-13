#!/bin/bash
# Large, non-uniform-delta cross-assembly RPC index test.
#
# Two Unity builds — one patched with scripts/patch-assembly-shift-indices.cs's
# non-uniform filler recipe (each of the 13 real Loader [RPC] methods shifted
# by a DIFFERENT amount, up to +90+) — exchange first-use + subsequent-use
# RPCs for all 13 methods (LargeDeltaIndexExperiment.cs). See
# docs/plans/large-delta-cross-assembly-index-test.md.
#
# Usage:
#   scripts/run-large-delta.sh [recipe]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER_DIR="$REPO_DIR/UnityProject/Builds/Linux"
PLAYER="$PLAYER_DIR/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
MANAGED="$PLAYER_DIR/Player_Data/Managed"
NS="unitynet"
PORT=7777
TIMEOUT=60
RECIPE="${1:-}"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
LABEL="LargeDelta"
PCAP="$CAPTURES_DIR/${LABEL}-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/${LABEL}-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/${LABEL}-${TIMESTAMP}-client.log"
mkdir -p "$CAPTURES_DIR"

echo "=== Large-Delta Cross-Binary Index Experiment ==="
echo "Two Unity builds with a large, NON-UNIFORM per-method [RPC] index delta exchange RPCs"
echo ""

# ── Step 1: Build the patcher if needed ──
PATCHER="$REPO_DIR/scripts/patch-assembly-shift-indices.exe"
CECIL_DLL="/usr/lib/mono/gac/Mono.Cecil/0.11.0.0__0738eb9f132ed756/Mono.Cecil.dll"

if [ ! -f "$CECIL_DLL" ]; then
    echo "ERROR: Mono.Cecil not found at $CECIL_DLL"
    exit 1
fi

if [ ! -f "$PATCHER" ] || [ "$REPO_DIR/scripts/patch-assembly-shift-indices.cs" -nt "$PATCHER" ]; then
    echo "Building patcher..."
    mcs -r:"$CECIL_DLL" \
        "$REPO_DIR/scripts/patch-assembly-shift-indices.cs" \
        -out:"$PATCHER"
fi

# ── Step 2: Build the experiments DLL if needed ──
if [ ! -f "$DLL_SRC" ] || find "$REPO_DIR/experiments" -name '*.cs' -newer "$DLL_SRC" | grep -q .; then
    echo "Building Experiments.dll..."
    bash "$REPO_DIR/experiments/build.sh"
fi

# ── Step 3: Create a patched copy of the Unity build ──
PATCHED_DIR="$PLAYER_DIR-largedelta"
echo "Creating patched build at $PATCHED_DIR ..."

if [ -d "$PATCHED_DIR" ]; then
    rm -rf "$PATCHED_DIR"
fi

cp -a "$PLAYER_DIR" "$PATCHED_DIR"

echo "Patching Assembly-CSharp.dll with non-uniform filler recipe..."
if [ -n "$RECIPE" ]; then
    mono "$PATCHER" \
        "$MANAGED/Assembly-CSharp.dll" \
        "$PATCHED_DIR/Player_Data/Managed/Assembly-CSharp.dll" \
        "$RECIPE"
else
    mono "$PATCHER" \
        "$MANAGED/Assembly-CSharp.dll" \
        "$PATCHED_DIR/Player_Data/Managed/Assembly-CSharp.dll"
fi

# ── Step 4: Show index differences ──
EXTRACTOR="$REPO_DIR/scripts/extract-method-indices.exe"
ORIG_INDICES="/tmp/large-delta-orig-indices.json"
PATCHED_INDICES="/tmp/large-delta-patched-indices.json"
if [ -f "$EXTRACTOR" ]; then
    echo ""
    echo "--- Original assembly indices ---"
    mono "$EXTRACTOR" "$MANAGED/Assembly-CSharp.dll" 2>/dev/null | tee "$ORIG_INDICES"
    echo ""
    echo "--- Patched assembly indices ---"
    mono "$EXTRACTOR" "$PATCHED_DIR/Player_Data/Managed/Assembly-CSharp.dll" 2>/dev/null | tee "$PATCHED_INDICES"
    echo ""
fi

# ── Step 5: Copy experiment DLL to both builds ──
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$PATCHED_DIR/Experiments"
cp "$DLL_SRC" "$PATCHED_DIR/Experiments/Experiments.dll"

# ── Step 6: Run the experiment ──
echo "Starting experiment..."
echo "  Server: PATCHED build (non-uniform shifted indices)"
echo "  Client: ORIGINAL build (normal indices)"

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

PCAP_TMP="/tmp/large-delta-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

sudo ip netns exec "$NS" "$PATCHED_DIR/Player.x86_64" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment LargeDeltaIndexExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 3

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment LargeDeltaIndexExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)

DEADLINE=$((SECONDS + TIMEOUT))
while [ $SECONDS -lt $DEADLINE ]; do
    SERVER_DONE=$(grep -c "EXPERIMENT_DONE" "$SERVER_LOG" 2>/dev/null || echo "0")
    CLIENT_DONE=$(grep -c "EXPERIMENT_DONE" "$CLIENT_LOG" 2>/dev/null || echo "0")
    if [ "$SERVER_DONE" -ge 1 ] && [ "$CLIENT_DONE" -ge 1 ]; then
        sleep 3
        break
    fi
    sleep 0.5
done

cleanup
trap - EXIT

sudo cp "$PCAP_TMP" "$PCAP" 2>/dev/null && sudo chmod 644 "$PCAP"
sudo rm -f "$PCAP_TMP"

echo ""
echo "--- Server (PATCHED) [RPC]/[Experiment] lines ---"
grep -E "\[Experiment\]|\[RPC\]" "$SERVER_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Client (ORIGINAL) [RPC]/[Experiment] lines ---"
grep -E "\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(none)"
echo ""

SERVER_RX=$(grep -c "RPC\]" "$SERVER_LOG" 2>/dev/null || echo "0")
CLIENT_RX=$(grep -c "RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "--- Summary ---"
echo "Server (patched) [RPC] log lines: $SERVER_RX"
echo "Client (original) [RPC] log lines: $CLIENT_RX"
echo ""
echo "Each side sends 26 RPCs (13 methods x 2 uses); expected 26 [RPC] lines each"
echo "if all first-use and subsequent-use dispatch correctly at the new, larger,"
echo "non-uniform per-method index deltas."
echo ""

echo "Pcap: $PCAP"
echo "Server log: $SERVER_LOG"
echo "Client log: $CLIENT_LOG"
echo "Original indices: $ORIG_INDICES"
echo "Patched indices: $PATCHED_INDICES"
