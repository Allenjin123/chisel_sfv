#!/bin/bash
# Display FIFO signal tracing table
# Shows key registers and control signals for DoubleBuffer FIFO
cd "$(dirname "$0")"
python3 python/trace_fifo_signals.py
