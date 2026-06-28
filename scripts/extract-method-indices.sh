#!/bin/bash
# Extract RPC method indices from a .NET assembly.
#
# Compiles and runs the Cecil-based extractor. Requires mono and mcs.
#
# Usage:
#   scripts/extract-method-indices.sh path/to/Assembly-CSharp.dll
#   scripts/extract-method-indices.sh path/to/Assembly-CSharp.dll --all
#
# Output: JSON array of RPC methods with their wire-format indices.
# Use the output to register method indices with registerMethodIndices().
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CS_SRC="$SCRIPT_DIR/extract-method-indices.cs"
EXE="$SCRIPT_DIR/extract-method-indices.exe"
CECIL="/usr/lib/mono/gac/Mono.Cecil/0.11.0.0__0738eb9f132ed756/Mono.Cecil.dll"

if [ ! -f "$CECIL" ]; then
    CECIL=$(find /usr/lib/mono -name 'Mono.Cecil.dll' 2>/dev/null | head -1)
    if [ -z "$CECIL" ]; then
        echo "ERROR: Mono.Cecil.dll not found. Install: apt install libmono-cecil-private-cil" >&2
        exit 1
    fi
fi

if [ ! -f "$EXE" ] || [ "$CS_SRC" -nt "$EXE" ]; then
    mcs -r:"$CECIL" "$CS_SRC" -out:"$EXE" 2>&1
fi

mono "$EXE" "$@"
