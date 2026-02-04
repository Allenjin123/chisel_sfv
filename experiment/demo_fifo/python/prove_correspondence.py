#!/usr/bin/env python3
"""
Sequential Signal Correspondence Prover for FIFO

This script proves correspondence between signals in optimized and unoptimized
versions of the FIFO design using Z3 SMT solver.

Note: For sequential circuits (with registers), full equivalence requires
considering state transitions. This script demonstrates symbolic verification
of combinational parts of the FIFO control logic.
"""

import re
from z3 import *

def extract_signals_from_verilog(filepath):
    """Extract signal definitions from Verilog"""
    signals = {}
    with open(filepath, 'r') as f:
        content = f.read()

    # Extract wire definitions with assignments
    # Pattern: wire <type> <name> = <expression>;
    wire_pattern = r'wire\s+(?:\[\d+:\d+\])?\s*(\w+)\s*=\s*([^;]+);'
    for match in re.finditer(wire_pattern, content):
        name, expr = match.groups()
        signals[name] = expr.strip()

    return signals

def parse_simple_expression(expr, context):
    """
    Parse simple Verilog expressions into Z3 formulas.
    This is a simplified parser for demonstration - a full parser would handle
    all Verilog operators and precedence.
    """
    expr = expr.strip()

    # Handle comparisons: signal == value
    if '==' in expr:
        parts = expr.split('==')
        if len(parts) == 2:
            left = parts[0].strip()
            right = parts[1].strip()

            # Get or create symbolic variables
            if left not in context:
                # Assume 2-bit for stateReg based on FIFO design
                context[left] = BitVec(left, 2)

            # Parse hex value like 2'h0, 2'h1, 2'h2
            if "'h" in right:
                hex_val = int(right.split("'h")[1], 16)
                return context[left] == BitVecVal(hex_val, 2)

    # Handle logic operations: signal & signal
    if '&' in expr and '==' not in expr:
        parts = expr.split('&')
        if len(parts) == 2:
            left = parts[0].strip()
            right = parts[1].strip()

            # Create boolean variables for control signals
            if left not in context:
                context[left] = Bool(left)
            if right not in context:
                context[right] = Bool(right)

            return And(context[left], context[right])

    # Handle negation: ~signal
    if expr.startswith('~'):
        inner = expr[1:].strip()
        if inner not in context:
            context[inner] = Bool(inner)
        return Not(context[inner])

    # Handle signal reference
    if expr in context:
        return context[expr]

    # Create new symbolic variable
    if expr not in context:
        context[expr] = Bool(expr)
    return context[expr]

def prove_correspondence(expr1, expr2, context):
    """Prove two expressions are equivalent"""
    try:
        s = Solver()
        # Try to prove they are NOT different (i.e., prove they are the same)
        s.add(expr1 != expr2)
        result = s.check()
        return result == unsat
    except:
        return None

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("FIFO Signal Correspondence Prover")
    print("=" * 70)
    print("\nNote: This is a simplified demonstration for sequential circuits.")
    print("Full verification requires considering state machine transitions.\n")

    # Extract signals from both versions
    print("Extracting signals from Verilog files...")
    unopt_signals = extract_signals_from_verilog('generated/unoptimized.sv')
    opt_signals = extract_signals_from_verilog('generated/optimized.sv')

    print(f"  Unoptimized: {len(unopt_signals)} wire definitions")
    print(f"  Optimized:   {len(opt_signals)} wire definitions")

    # Create shared symbolic context
    context = {
        'stateReg': BitVec('stateReg', 2),
        'io_enq_valid': Bool('io_enq_valid'),
        'io_deq_ready': Bool('io_deq_ready'),
        'io_enq_ready': Bool('io_enq_ready'),
        'io_deq_valid': Bool('io_deq_valid'),
    }

    print("\n" + "-" * 70)
    print("Key Control Signal Correspondences:")
    print("-" * 70)

    # Define signal pairs to check (common control signals in FIFO)
    pairs = [
        ('_io_enq_ready_T', '_io_enq_ready_T',
         'State check: empty (stateReg == 0)'),
        ('_io_deq_valid_T', '_io_deq_valid_T',
         'State check: one (stateReg == 1)'),
        ('_GEN_0', '_GEN_0',
         'Control: deq_ready AND enq_valid'),
        ('_GEN_1', '_GEN_1',
         'Control: NOT deq_ready AND enq_valid'),
    ]

    results = []
    for unopt_sig, opt_sig, desc in pairs:
        if unopt_sig in unopt_signals and opt_sig in opt_signals:
            unopt_expr = unopt_signals[unopt_sig]
            opt_expr = opt_signals[opt_sig]

            print(f"\n{desc}:")
            print(f"  Unoptimized: {unopt_sig} = {unopt_expr}")
            print(f"  Optimized:   {opt_sig} = {opt_expr}")

            # Check if expressions are textually identical
            if unopt_expr == opt_expr:
                print(f"  Status: IDENTICAL (same expression)")
                results.append((desc, 'IDENTICAL'))
            else:
                # Try symbolic verification
                try:
                    z3_unopt = parse_simple_expression(unopt_expr, context)
                    z3_opt = parse_simple_expression(opt_expr, context)
                    equiv = prove_correspondence(z3_unopt, z3_opt, context)

                    if equiv is True:
                        print(f"  Status: PROVEN (symbolically equivalent)")
                        results.append((desc, 'PROVEN'))
                    elif equiv is False:
                        print(f"  Status: DIFFERENT (not equivalent)")
                        results.append((desc, 'DIFFERENT'))
                    else:
                        print(f"  Status: UNKNOWN (cannot verify)")
                        results.append((desc, 'UNKNOWN'))
                except Exception as e:
                    print(f"  Status: PARSE_ERROR ({str(e)})")
                    results.append((desc, 'ERROR'))
        else:
            missing = []
            if unopt_sig not in unopt_signals:
                missing.append("unoptimized")
            if opt_sig not in opt_signals:
                missing.append("optimized")
            print(f"\n{desc}:")
            print(f"  Status: SKIPPED (signal not found in {', '.join(missing)})")
            results.append((desc, 'SKIPPED'))

    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)

    status_count = {}
    for desc, status in results:
        status_count[status] = status_count.get(status, 0) + 1

    for status, count in sorted(status_count.items()):
        print(f"  {status}: {count}")

    print("\n" + "=" * 70)
    print("\nFor complete sequential equivalence, use Yosys with equiv_induct:")
    print("  yosys yosys_equiv.ys")
    print("=" * 70)
