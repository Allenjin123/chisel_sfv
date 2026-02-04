#!/bin/bash
# Run Yosys expression tracing for DoubleBufferFifo
cd "$(dirname "$0")"
yosys yosys/trace_expr2.ys
