#!/bin/bash
# Run an experiment using the Unity 5.5.6f1 player.
# Thin wrapper around run-experiment.sh that swaps the player and DLL paths.
#
# Usage: ./run-experiment-5.5.sh <experiment-class-name> [extra-args...]

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAYER_55="$REPO_DIR/UnityProject/Builds/Linux-5.5.6f1/Player.x86_64"
DLL_55="$REPO_DIR/experiments/Experiments-5.5.dll"

[ -f "$PLAYER_55" ] || { echo "ERROR: 5.5.6f1 player not found at $PLAYER_55"; exit 1; }
[ -f "$DLL_55" ] || { echo "ERROR: Experiments-5.5.dll not built. Run: bash experiments/build-5.5.sh"; exit 1; }

export PLAYER_OVERRIDE="$PLAYER_55"
export DLL_OVERRIDE="$DLL_55"
exec "$REPO_DIR/run-experiment.sh" "$@"
