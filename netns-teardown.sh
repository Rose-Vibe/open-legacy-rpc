#!/bin/bash
# Tears down the "unitynet" network namespace and removes associated rules.
#
# Run with: sudo bash netns-teardown.sh

set -euo pipefail

NS="unitynet"
VETH_HOST="veth-unet-h"
NS_IP="10.200.1.2"
SUBNET="24"

echo "=== Tearing down network namespace '$NS' ==="

# Remove iptables rules (ignore errors if they don't exist)
iptables -t nat -D POSTROUTING -s "$NS_IP/$SUBNET" -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -s "$NS_IP/$SUBNET" -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -d "$NS_IP/$SUBNET" -j ACCEPT 2>/dev/null || true

# Remove namespace (also removes veth-unity automatically)
ip netns del "$NS" 2>/dev/null || true
ip link del "$VETH_HOST" 2>/dev/null || true

# Remove sudoers rule
rm -f /etc/sudoers.d/unitynet-netns

echo "=== Teardown complete ==="
