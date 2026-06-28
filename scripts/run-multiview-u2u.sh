#!/bin/bash
# Run MultiViewIndexExperiment: capture RPCs sent via multiple NetworkViews
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777
TIMEOUT=40

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
PCAP="$CAPTURES_DIR/MultiViewIndex-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/MultiViewIndex-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/MultiViewIndex-${TIMESTAMP}-client.log"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments" "$CAPTURES_DIR"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "=== MultiView Index U2U Capture ==="

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

PCAP_TMP="/tmp/multiview-u2u-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment MultiViewIndexExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 3

sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment MultiViewIndexExperiment \
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
echo "--- Unity server ---"
grep -E "\[Experiment\]|\[RPC\]" "$SERVER_LOG" 2>/dev/null || echo "(no matching lines)"
echo ""
echo "--- Unity client ---"
grep -E "\[Experiment\]|\[RPC\]" "$CLIENT_LOG" 2>/dev/null || echo "(no matching lines)"
echo ""

sudo cp "$PCAP_TMP" "$PCAP" && sudo chmod 644 "$PCAP"
echo "Pcap saved to: $PCAP"

echo ""
echo "--- Pcap analysis ---"
python3 << PYEOF
import sys, struct
sys.path.insert(0, '$REPO_DIR')
from protocol.raknet_transport import unpack_datagram

pcap_file = '$PCAP'
with open(pcap_file, 'rb') as f:
    magic = struct.unpack('<I', f.read(4))[0]
    endian = '<' if magic == 0xa1b2c3d4 else '>'
    _, _, _, _, snaplen, network = struct.unpack(endian + 'HHiIII', f.read(20))

    rpc_num = 0
    while True:
        hdr = f.read(16)
        if len(hdr) < 16:
            break
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + 'IIII', hdr)
        data = f.read(incl_len)
        if len(data) < incl_len:
            break

        if network == 113:
            ip_start = 16
        elif network in (0, 101):
            ip_start = 4
        elif network == 1:
            ip_start = 14
        else:
            ip_start = 4

        if len(data) < ip_start + 28:
            continue
        ip_hdr = data[ip_start:]
        if (ip_hdr[0] >> 4) != 4 or ip_hdr[9] != 17:
            continue
        ip_ihl = (ip_hdr[0] & 0xf) * 4
        udp_start = ip_start + ip_ihl
        if len(data) < udp_start + 8:
            continue
        src_port = struct.unpack('>H', data[udp_start:udp_start+2])[0]
        dst_port = struct.unpack('>H', data[udp_start+2:udp_start+4])[0]
        udp_payload = data[udp_start+8:]

        if not udp_payload:
            continue
        result = unpack_datagram(udp_payload)
        if result[0] != 'data':
            continue
        _, ts, seq, messages = result
        for msg in messages:
            if not msg.payload or msg.payload[0] != 0x1b:
                continue
            if len(msg.payload) < 10 or msg.payload[9] != 0x0b:
                continue
            rpc_num += 1
            all_bits = ''.join(f'{b:08b}' for b in msg.payload)
            first_use = int(all_bits[80])
            direction = "C->S" if dst_port == $PORT else "S->C"
            if first_use:
                ref_bits = int(all_bits[81:88], 2)
                # Try to extract method name
                name_hex = msg.payload[10:].hex()
                print(f"  #{rpc_num} [{direction}] FIRST-USE  ref=0x{ref_bits:02x}  raw[10:]={name_hex}")
            else:
                idx = int(all_bits[81:88], 2)
                reserved = int(all_bits[88:104], 2)
                print(f"  #{rpc_num} [{direction}] SUBSEQUENT idx=0x{idx:02x} ({idx})  reserved=0x{reserved:04x}  raw={msg.payload[:20].hex()}")
    print(f"\nTotal RPC messages: {rpc_num}")
PYEOF
