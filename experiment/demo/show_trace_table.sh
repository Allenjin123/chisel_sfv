#!/bin/bash
# Display signal tracing summary table
# Shows correspondence: Optimized Verilog → Unoptimized Verilog → Chisel Source
cd "$(dirname "$0")"
python3 python/trace_all_signals.py
