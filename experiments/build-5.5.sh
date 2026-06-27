#!/bin/bash
# Build the experiments DLL against the Unity 5.5.6f1 player's managed assemblies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANAGED="$SCRIPT_DIR/../UnityProject/Builds/Linux-5.5.6f1/Player_Data/Managed"

if [ ! -f "$MANAGED/UnityEngine.dll" ]; then
    echo "ERROR: Unity 5.5.6f1 player not found at $MANAGED"
    exit 1
fi

SOURCES=()
for f in "$SCRIPT_DIR"/*Experiment.cs; do
    [ "$f" = "$SCRIPT_DIR/IExperiment.cs" ] && continue
    SOURCES+=("$f")
done

mcs -target:library -out:"$SCRIPT_DIR/Experiments-5.5.dll" \
    -r:"$MANAGED/UnityEngine.dll" \
    -r:"$MANAGED/Assembly-CSharp.dll" \
    -nowarn:0618 \
    "${SOURCES[@]}"

echo "Built Experiments-5.5.dll ($(wc -c < "$SCRIPT_DIR/Experiments-5.5.dll") bytes)"
