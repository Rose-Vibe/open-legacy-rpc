#!/bin/bash
# Start a Unity server with the specified experiment, no client.
# The server runs in the network namespace and waits for external connections.
#
# Usage: ./run-server-only.sh <experiment-name>

set -euo pipefail

EXPERIMENT="${1:?Usage: $0 <experiment-name>}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAYER="$REPO_DIR/UnityProject/Builds/Linux/Player.x86_64"
DLL_SRC="$REPO_DIR/experiments/Experiments.dll"
NS="unitynet"
PORT=7777

[ -f "$PLAYER" ] || { echo "ERROR: Player not built at $PLAYER"; exit 1; }
[ -f "$DLL_SRC" ] || { echo "ERROR: Experiments.dll not built."; exit 1; }
ip netns list | grep -q "$NS" || { echo "ERROR: Namespace '$NS' not found."; exit 1; }

PLAYER_DIR="$(dirname "$PLAYER")"
mkdir -p "$PLAYER_DIR/Experiments"
cp "$DLL_SRC" "$PLAYER_DIR/Experiments/Experiments.dll"

echo "Starting Unity server with experiment: $EXPERIMENT"
echo "  Port: $PORT"
echo "  Namespace: $NS"
echo "  Press Ctrl+C to stop"
echo ""

exec sudo ip netns exec "$NS" "$PLAYER" \
    -batchmode -nographics -logFile - \
    -- --server --port "$PORT" --experiment "$EXPERIMENT"
