#!/bin/bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER_DIR="$REPO_DIR/UnityProject/Builds/Linux"
PLAYER="$PLAYER_DIR/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
MANAGED="$PLAYER_DIR/Player_Data/Managed"
NS="unitynet"
PORT=7777
TIMEOUT=40

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
PCAP="$CAPTURES_DIR/CrossBinary-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/CrossBinary-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/CrossBinary-${TIMESTAMP}-client.log"
mkdir -p "$CAPTURES_DIR"

echo "=== Cross-Binary Index Experiment ==="
echo "Two Unity builds with different [RPC] method counts exchange RPCs"
echo ""

# ── Step 1: Build the patcher if needed ──
PATCHER="$REPO_DIR/scripts/patch-assembly-shift-indices.exe"
CECIL_DLL="/usr/lib/mono/gac/Mono.Cecil/0.11.0.0__0738eb9f132ed756/Mono.Cecil.dll"

if [ ! -f "$CECIL_DLL" ]; then
    echo "ERROR: Mono.Cecil not found at $CECIL_DLL"
    echo "Install with: sudo apt install libmono-cecil-cil-dev"
    exit 1
fi

if [ ! -f "$PATCHER" ] || [ "$REPO_DIR/scripts/patch-assembly-shift-indices.cs" -nt "$PATCHER" ]; then
    echo "Building patcher..."
    mcs -r:"$CECIL_DLL" \
        "$REPO_DIR/scripts/patch-assembly-shift-indices.cs" \
        -out:"$PATCHER"
fi

# ── Step 2: Create a patched copy of the Unity build ──
PATCHED_DIR="$PLAYER_DIR-patched"
echo "Creating patched build at $PATCHED_DIR ..."

if [ -d "$PATCHED_DIR" ]; then
    rm -rf "$PATCHED_DIR"
fi

cp -a "$PLAYER_DIR" "$PATCHED_DIR"

echo "Patching Assembly-CSharp.dll (adding 3 extra [RPC] methods)..."
mono "$PATCHER" \
    "$MANAGED/Assembly-CSharp.dll" \
    "$PATCHED_DIR/Player_Data/Managed/Assembly-CSharp.dll" \
    3

# ── Step 3: Show index differences ──
EXTRACTOR="$REPO_DIR/scripts/extract-method-indices.exe"
if [ -f "$EXTRACTOR" ]; then
    echo ""
    echo "--- Original assembly indices ---"
    mono "$EXTRACTOR" "$MANAGED/Assembly-CSharp.dll" 2>/dev/null | head -20
    echo ""
    echo "--- Patched assembly indices ---"
    mono "$EXTRACTOR" "$PATCHED_DIR/Player_Data/Managed/Assembly-CSharp.dll" 2>/dev/null | head -20
    echo ""
fi

# ── Step 4: Copy experiment DLL to both builds ──
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"
mkdir -p "$PATCHED_DIR/Experiments"
cp "$DLL_SRC" "$PATCHED_DIR/Experiments/Experiments.dll"

# ── Step 5: Run the experiment ──
echo "Starting experiment..."
echo "  Server: PATCHED build (shifted indices)"
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

# Start pcap capture
PCAP_TMP="/tmp/cross-binary-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

# Start PATCHED Unity as server
sudo ip netns exec "$NS" "$PATCHED_DIR/Player.x86_64" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment CrossBinaryIndexExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 3

# Start ORIGINAL Unity as client
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment CrossBinaryIndexExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)

# Wait for both to finish
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

echo ""
echo "--- Server (PATCHED) ---"
grep -E "\[Experiment\]|\[RPC\]" "$SERVER_LOG" 2>/dev/null || echo "(none)"
echo ""
echo "--- Client (ORIGINAL) ---"
grep -E "\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(none)"
echo ""

SERVER_RX=$(grep -c "RECEIVED" "$SERVER_LOG" 2>/dev/null || echo "0")
CLIENT_RX=$(grep -c "RECEIVED" "$CLIENT_LOG" 2>/dev/null || echo "0")
echo "--- Summary ---"
echo "Server (patched) received: $SERVER_RX RPCs from client"
echo "Client (original) received: $CLIENT_RX RPCs from server"
echo ""
echo "Each side sends 9 RPCs (3×RPC_Int + 2×RPC_Float + 2×RPC_String + 2×RPC_Alpha)"
echo "Expected if learning works: both receive 9"
echo "Expected if pre-computed:   both receive ~4 (only first-use of each method)"
echo ""

sudo cp "$PCAP_TMP" "$PCAP" 2>/dev/null && sudo chmod 644 "$PCAP"
echo "Pcap: $PCAP"
echo "Server log: $SERVER_LOG"
echo "Client log: $CLIENT_LOG"

# ── Step 6: Analyze pcap for index values ──
echo ""
echo "--- Pcap Analysis: method indices from each direction ---"
python3 << PYEOF
import sys, struct
sys.path.insert(0, '$REPO_DIR')
from protocol.raknet_transport import unpack_datagram

with open('$PCAP', 'rb') as f:
    magic = struct.unpack('<I', f.read(4))[0]
    endian = '<' if magic == 0xa1b2c3d4 else '>'
    f.read(20)  # rest of global header
    rpc_num = 0
    while True:
        hdr = f.read(16)
        if len(hdr) < 16: break
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + 'IIII', hdr)
        data = f.read(incl_len)
        if len(data) < incl_len: break
        if len(data) < 42 + 10: continue
        # Linux cooked capture or loopback
        ip_start = 4  # loopback
        ip_hdr = data[ip_start:]
        if (ip_hdr[0] >> 4) != 4: continue
        if ip_hdr[9] != 17: continue
        ip_ihl = (ip_hdr[0] & 0xf) * 4
        udp_start = ip_start + ip_ihl
        if len(data) < udp_start + 8: continue
        src_port = struct.unpack('>H', data[udp_start:udp_start+2])[0]
        dst_port = struct.unpack('>H', data[udp_start+2:udp_start+4])[0]
        udp_payload = data[udp_start+8:]
        if not udp_payload: continue
        result = unpack_datagram(udp_payload)
        if result[0] != 'data': continue
        for msg in result[3]:
            if not msg.payload or msg.payload[0] != 0x1b: continue
            if len(msg.payload) < 10 or msg.payload[9] != 0x0b: continue
            rpc_num += 1
            all_bits = ''.join(f'{b:08b}' for b in msg.payload)
            first_use = int(all_bits[80])
            direction = "C->S" if dst_port == $PORT else "S->C"
            if first_use:
                ref = int(all_bits[81:88], 2)
                tag_start = 160
                li = int(all_bits[104:112], 2)
                method_id_bits = li * 4
                hash_extra = method_id_bits - 48
                tag_pos = 160 + hash_extra
                if tag_pos + 4 <= len(all_bits):
                    tag = int(all_bits[tag_pos:tag_pos+4], 2)
                else:
                    tag = -1
                print(f"  #{rpc_num:2d} [{direction}] FIRST-USE  tag=0x{tag:x}")
            else:
                idx_bits = all_bits[81:88]
                idx = int(idx_bits, 2)
                print(f"  #{rpc_num:2d} [{direction}] SUBSEQUENT idx=0x{idx*2:02x} ({idx*2})")
    print(f"\nTotal RPC messages: {rpc_num}")
PYEOF
