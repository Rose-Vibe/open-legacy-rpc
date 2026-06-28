#!/bin/bash
# Capture Unity-to-Unity subsequent-use RPCs via tshark.
# Runs two Unity instances (server + client) in the network namespace.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777
TIMEOUT=30

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CAPTURES_DIR="$REPO_DIR/captures"
PCAP="$CAPTURES_DIR/MethodIndexU2U-${TIMESTAMP}.pcap"
SERVER_LOG="$CAPTURES_DIR/MethodIndexU2U-${TIMESTAMP}-server.log"
CLIENT_LOG="$CAPTURES_DIR/MethodIndexU2U-${TIMESTAMP}-client.log"

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments" "$CAPTURES_DIR"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "=== Method Index U2U Capture ==="

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

# Start tshark capture on loopback inside the namespace (U2U traffic stays within namespace)
PCAP_TMP="/tmp/method-index-u2u-capture.pcap"
sudo ip netns exec "$NS" tshark -i lo -f 'udp' -F pcap -w "$PCAP_TMP" > /dev/null 2>&1 &
PIDS+=($!)
sleep 1

# Unity server
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment MethodIndexU2UExperiment \
    > "$SERVER_LOG" 2>&1 &
PIDS+=($!)
sleep 3

# Unity client
sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --client --port "$PORT" --experiment MethodIndexU2UExperiment \
    > "$CLIENT_LOG" 2>&1 &
PIDS+=($!)
CLIENT_PID=${PIDS[-1]}

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
echo "--- Pcap analysis ---"

# Copy pcap from tmp
sudo cp "$PCAP_TMP" "$PCAP" && sudo chmod 644 "$PCAP"
echo "Pcap saved to: $PCAP"

# Analyze the pcap for RPC messages
python3 << PYEOF
import sys, struct
sys.path.insert(0, '$REPO_DIR')
from protocol.raknet_transport import unpack_datagram

pcap_file = '$PCAP'
with open(pcap_file, 'rb') as f:
    magic = struct.unpack('<I', f.read(4))[0]
    endian = '<' if magic == 0xa1b2c3d4 else '>'
    version_major, version_minor, thiszone, sigfigs, snaplen, network = struct.unpack(endian + 'HHiIII', f.read(20))

    rpc_num = 0
    while True:
        hdr = f.read(16)
        if len(hdr) < 16:
            break
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + 'IIII', hdr)
        data = f.read(incl_len)
        if len(data) < incl_len:
            break

        # Parse link layer
        if network == 113:  # Linux cooked
            ip_start = 16
        elif network in (0, 101):  # Loopback / Raw IP
            ip_start = 4
        elif network == 1:  # Ethernet
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
                print(f"  #{rpc_num} [{direction}] FIRST-USE  ref_bits=0x{ref_bits:02x}  raw={msg.payload[:18].hex()}")
            else:
                idx = int(all_bits[81:88], 2)
                reserved = int(all_bits[88:104], 2)
                print(f"  #{rpc_num} [{direction}] SUBSEQUENT idx=0x{idx:02x} ({idx})  reserved=0x{reserved:04x}  raw={msg.payload[:18].hex()}")
    print(f"\nTotal RPC messages: {rpc_num}, link type: {network}")
PYEOF
