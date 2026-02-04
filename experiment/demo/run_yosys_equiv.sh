#!/bin/bash
# Run Yosys equivalence checking
cd "$(dirname "$0")"
yosys yosys/yosys_equiv.ys
