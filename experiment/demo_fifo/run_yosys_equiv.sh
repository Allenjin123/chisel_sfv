#!/bin/bash
# Run Yosys equivalence checking for DoubleBufferFifo
cd "$(dirname "$0")"
yosys yosys/yosys_equiv.ys
