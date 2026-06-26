#!/bin/bash
# Build the experiments DLL against the Unity player's managed assemblies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANAGED="$SCRIPT_DIR/../UnityProject/Builds/Linux/Player_Data/Managed"

if [ ! -f "$MANAGED/UnityEngine.dll" ]; then
    echo "ERROR: Unity player not built yet. Build UnityProject first."
    exit 1
fi

SOURCES=()
for f in "$SCRIPT_DIR"/*Experiment.cs; do
    [ "$f" = "$SCRIPT_DIR/IExperiment.cs" ] && continue
    SOURCES+=("$f")
done

mcs -target:library -out:"$SCRIPT_DIR/Experiments.dll" \
    -r:"$MANAGED/UnityEngine.dll" \
    -r:"$MANAGED/UnityEngine.CoreModule.dll" \
    -r:"$MANAGED/Assembly-CSharp.dll" \
    -nowarn:0618 \
    "${SOURCES[@]}"

echo "Built Experiments.dll ($(wc -c < "$SCRIPT_DIR/Experiments.dll") bytes)"
