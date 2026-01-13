#!/usr/bin/env python3
"""
Signal Correspondence Prover

Parses combined.mlir and proves correspondence between signals
by building Z3 expressions directly from IR operations.
"""

import re
from z3 import *

def parse_mlir(filepath):
    """Parse MLIR and extract operations"""
    with open(filepath, 'r') as f:
        content = f.read()

    ops = []
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('}'):
            continue

        # Parse: %name = op_type operands : type
        match = re.match(r'%(\w+)\s*=\s*(\w+\.\w+)\s+(.+)', line)
        if match:
            name, op_type, rest = match.groups()
            ops.append((name, op_type, rest))

    return ops

def build_z3_expr(ops, inputs):
    """Build Z3 expressions from parsed operations"""
    symbols = dict(inputs)  # Start with input symbols

    for name, op_type, rest in ops:
        if op_type == 'hw.constant':
            # Parse: -1 : i16 or false
            if 'false' in rest:
                symbols[name] = BitVecVal(0, 1)
            else:
                match = re.match(r'(-?\d+)\s*:\s*i(\d+)', rest)
                if match:
                    val, width = int(match.group(1)), int(match.group(2))
                    symbols[name] = BitVecVal(val, width)

        elif op_type == 'comb.concat':
            # Parse: %a, %b : i8, i8
            match = re.match(r'%(\w+),\s*%(\w+)\s*:', rest)
            if match:
                a, b = match.groups()
                symbols[name] = Concat(symbols[a], symbols[b])

        elif op_type == 'comb.mul':
            # Parse: %a, %b : i16
            match = re.match(r'%(\w+),\s*%(\w+)\s*:', rest)
            if match:
                a, b = match.groups()
                symbols[name] = symbols[a] * symbols[b]

        elif op_type == 'comb.add':
            # Parse: %a, %b : i16 or %a, %b, %c, %d : i16
            operands = re.findall(r'%(\w+)', rest.split(':')[0])
            result = symbols[operands[0]]
            for op in operands[1:]:
                result = result + symbols[op]
            symbols[name] = result

        elif op_type == 'comb.xor':
            # Parse: %a, %b : i8
            match = re.match(r'%(\w+),\s*%(\w+)\s*:', rest)
            if match:
                a, b = match.groups()
                symbols[name] = symbols[a] ^ symbols[b]

        elif op_type == 'comb.extract':
            # Parse: %a from 0 : (i17) -> i16
            match = re.match(r'%(\w+)\s+from\s+(\d+)\s*:\s*\(i(\d+)\)\s*->\s*i(\d+)', rest)
            if match:
                src, low, in_w, out_w = match.groups()
                low, out_w = int(low), int(out_w)
                symbols[name] = Extract(low + out_w - 1, low, symbols[src])

    return symbols

def prove_correspondence(symbols, sig1, sig2):
    """Prove two signals are equivalent"""
    s = Solver()
    s.add(symbols[sig1] != symbols[sig2])
    result = s.check()
    return result == unsat

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("Signal Correspondence Prover (from combined.mlir)")
    print("=" * 70)

    # Parse the combined IR
    ops = parse_mlir('generated/combined.mlir')
    print(f"\nParsed {len(ops)} operations from combined.mlir")

    # Define symbolic inputs (shared between both paths)
    inputs = {
        'io_in0': BitVec('io_in0', 8),
        'io_in1': BitVec('io_in1', 8),
        'io_in4': BitVec('io_in4', 8),
        'io_in8': BitVec('io_in8', 8),
    }

    # Build Z3 expressions from IR
    symbols = build_z3_expr(ops, inputs)
    print(f"Built {len(symbols)} Z3 expressions")

    # Signal pairs to check (from combined.mlir)
    pairs = [
        ('c_2', 'v_8', 'multiplication (c_op5 ↔ v_mul)'),
        ('c_9', 'v_9', 'NOT of mul (c_not3 ↔ v_not_mul)'),
        ('c_21', 'v_10', 'final output (c_mapred6 ↔ v_result)'),
    ]

    print("\n" + "-" * 70)
    print("Proving signal correspondences:")
    print("-" * 70)

    for c_sig, v_sig, desc in pairs:
        if c_sig in symbols and v_sig in symbols:
            equiv = prove_correspondence(symbols, c_sig, v_sig)
            status = "PROVEN" if equiv else "FAILED"
            print(f"\n%{c_sig} ↔ %{v_sig} ({desc})")
            print(f"  Status: {status}")
        else:
            print(f"\n%{c_sig} ↔ %{v_sig} ({desc})")
            print(f"  Status: SKIPPED (signal not found)")

    print("\n" + "=" * 70)
