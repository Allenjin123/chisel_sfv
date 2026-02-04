#!/bin/bash
# Run formal signal correspondence tracing using Yosys
#
# This script uses Yosys equivalence checking to formally prove which signals
# in the optimized Verilog correspond to signals in the unoptimized version.
#
# Key features:
# - Uses equiv_induct for sequential circuits (handles registers)
# - Uses equiv_simple for combinational logic
# - SAT solving to prove functional equivalence (not just name matching)
#
# Usage:
#   ./run_formal_trace.sh           # Basic run
#   ./run_formal_trace.sh --cross   # Also discover cross-signal equivalences (slower)

cd "$(dirname "$0")"

echo "=================================================="
echo "Formal Signal Correspondence Tracer"
echo "=================================================="
echo ""

# Check if yosys is available
if ! command -v yosys &> /dev/null; then
    echo "Error: yosys is not installed or not in PATH"
    exit 1
fi

# Pass any additional arguments to the Python script
python3 python/trace_signals_formal.py \
    --unopt generated/unoptimized.sv \
    --opt generated/optimized.sv \
    --module DoubleBuffer \
    --chisel-src src/main/scala \
    --verbose \
    "$@"

echo ""
echo "Done."
