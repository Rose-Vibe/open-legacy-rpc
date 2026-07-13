#!/bin/bash
# Sets up the "unitynet" network namespace so Unity processes can run
# without hitting RakNet's ~10 IP address limit.
#
# This namespace is designed for protocol reverse-engineering: both a Unity
# server and client(s) run inside the same namespace on loopback, and tshark
# can capture all their traffic on the veth interface from the host side.
#
# Run once with: sudo bash netns-setup.sh
#
# After setup, run Unity processes without sudo prompts:
#   sudo ip netns exec unitynet ./Player.x86_64 -batchmode -nographics -logFile -
#
# Capture traffic from the HOST side (no root needed after dumpcap setcap):
#   tshark -i veth-unet-h -f "udp" -w /tmp/unity.pcap

set -euo pipefail

NS="unitynet"
VETH_HOST="veth-unet-h"
VETH_NS="veth-unet-ns"
HOST_IP="10.200.1.1"
NS_IP="10.200.1.2"
SUBNET="24"
USER="${SUDO_USER:-$(whoami)}"

echo "=== Setting up network namespace '$NS' ==="

# Clean up if already exists
ip netns del "$NS" 2>/dev/null || true
ip link del "$VETH_HOST" 2>/dev/null || true

# Create namespace and veth pair
ip netns add "$NS"
ip link add "$VETH_HOST" type veth peer name "$VETH_NS"
ip link set "$VETH_NS" netns "$NS"

# Configure host side
ip addr add "$HOST_IP/$SUBNET" dev "$VETH_HOST"
ip link set "$VETH_HOST" up

# Configure namespace side
ip netns exec "$NS" ip link set lo up
ip netns exec "$NS" ip addr add "$NS_IP/$SUBNET" dev "$VETH_NS"
ip netns exec "$NS" ip link set "$VETH_NS" up

# Enable IP forwarding (idempotent)
sysctl -w net.ipv4.ip_forward=1 > /dev/null

# Allow outbound from namespace (for Unity license checks, etc.)
iptables -t nat -A POSTROUTING -s "$NS_IP/$SUBNET" -j MASQUERADE
iptables -A FORWARD -s "$NS_IP/$SUBNET" -j ACCEPT
iptables -A FORWARD -d "$NS_IP/$SUBNET" -j ACCEPT
ip netns exec "$NS" ip route add default via "$HOST_IP"

# Grant dumpcap raw capture so tshark works without root
setcap cap_net_raw,cap_net_admin+eip "$(which dumpcap)" 2>/dev/null || true

# Add sudoers rule: allow running commands in the namespace without password
IP_PATH="$(which ip)"
SUDOERS_FILE="/etc/sudoers.d/unitynet-netns"
cat > "$SUDOERS_FILE" << EOF
# Allow $USER to run commands in the unitynet network namespace without a password
$USER ALL=(ALL) NOPASSWD: $IP_PATH netns exec $NS *
# Allow kill/cp/chown/rm for experiment runner cleanup
$USER ALL=(ALL) NOPASSWD: /usr/bin/kill *
$USER ALL=(ALL) NOPASSWD: /bin/kill *
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp *
$USER ALL=(ALL) NOPASSWD: /usr/bin/chown *
$USER ALL=(ALL) NOPASSWD: /usr/bin/rm -f /tmp/experiment-capture-*
EOF
chmod 440 "$SUDOERS_FILE"

# Verify
echo ""
echo "Namespace IPs:"
ip netns exec "$NS" ip -4 addr show | grep inet
echo ""
echo "Connectivity test:"
ip netns exec "$NS" ping -c1 -W1 "$HOST_IP" > /dev/null && echo "  namespace -> host: OK" || echo "  namespace -> host: FAILED"
echo ""
echo "=== Setup complete ==="
echo ""
echo "Run Unity processes inside the namespace:"
echo "  sudo ip netns exec $NS ./Player.x86_64 -batchmode -nographics -logFile -"
echo ""
echo "Capture traffic from the host (no root needed):"
echo "  tshark -i $VETH_HOST -f 'udp' -w /tmp/unity.pcap"
echo ""
echo "To tear down: sudo bash netns-teardown.sh"
