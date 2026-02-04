#!/bin/bash

# Test all Yosys and Python scripts to verify they work correctly
# Run from ~/chisel_sfv/experiment/demo directory

echo "========================================"
echo "Testing all scripts in demo directory"
echo "========================================"
echo ""

# Check if we're in the right directory
if [ ! -d "generated" ]; then
    echo "Error: 'generated' directory not found"
    echo "Make sure you're running this from ~/chisel_sfv/experiment/demo"
    exit 1
fi

# Check if required files exist
echo "Checking required files..."
REQUIRED_FILES=(
    "generated/unoptimized.sv"
    "generated/optimized.sv"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "  ✗ Missing: $file"
        exit 1
    else
        echo "  ✓ Found: $file"
    fi
done
echo ""

# Test Yosys scripts
echo "========================================"
echo "Testing Yosys scripts (.ys)"
echo "========================================"
echo ""

YOSYS_SCRIPTS=(
    "yosys/yosys_equiv.ys"
    "yosys/trace_expr2.ys"
    "yosys/list_signals.ys"
    "yosys/print_wires.ys"
    "yosys/list_intermediate_signals.ys"
)

for script in "${YOSYS_SCRIPTS[@]}"; do
    if [ ! -f "$script" ]; then
        echo "⊘ $script - NOT FOUND"
        continue
    fi

    echo "Testing: $script"
    if yosys -Q "$script" > /dev/null 2>&1; then
        echo "  ✓ $script - PASSED"
    else
        echo "  ✗ $script - FAILED"
        echo "    Run 'yosys $script' to see error details"
    fi
    echo ""
done

# Test Python scripts
echo "========================================"
echo "Testing Python scripts (.py)"
echo "========================================"
echo ""

echo "Testing: python/extract_intermediate_signals.py"
if [ -f "python/extract_intermediate_signals.py" ]; then
    if python3 python/extract_intermediate_signals.py generated/optimized.sv Figure5Example > /dev/null 2>&1; then
        echo "  ✓ extract_intermediate_signals.py - PASSED"
    else
        echo "  ✗ extract_intermediate_signals.py - FAILED"
    fi
else
    echo "  ⊘ extract_intermediate_signals.py - NOT FOUND"
fi
echo ""

echo "Testing: python/trace_all_signals.py"
if [ -f "python/trace_all_signals.py" ]; then
    if python3 python/trace_all_signals.py > /dev/null 2>&1; then
        echo "  ✓ trace_all_signals.py - PASSED"
    else
        echo "  ✗ trace_all_signals.py - FAILED"
    fi
else
    echo "  ⊘ trace_all_signals.py - NOT FOUND"
fi
echo ""

echo "========================================"
echo "Test suite completed"
echo "========================================"
