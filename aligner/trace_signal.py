#!/usr/bin/env python3
"""
Signal Correspondence Tracer

Given a signal location in optimized.sv, formally proves which signals in
unoptimized.sv are equivalent, then reports the Chisel source annotations.

Usage:
    python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 21.23-39
    python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 21.23-39 --bounded
    python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 21.23-39 --module DoubleBuffer
"""

import subprocess
import re
import sys
import os
import argparse
import tempfile
from pathlib import Path


def detect_module_name(verilog_file):
    """Auto-detect the first module name from a Verilog file."""
    with open(verilog_file, 'r') as f:
        for line in f:
            match = re.match(r'\s*module\s+(\w+)', line)
            if match:
                return match.group(1)
    return None


def get_other_modules(verilog_file, target_module):
    """Find all module names in a Verilog file except the target module."""
    modules = []
    with open(verilog_file, 'r') as f:
        for line in f:
            match = re.match(r'\s*module\s+(\w+)', line)
            if match and match.group(1) != target_module:
                modules.append(match.group(1))
    return modules


def get_source_location(signal_name, verilog_file):
    """Extract source location annotation for a signal from Verilog comments.

    Handles two annotation formats:
      - @[src/main/scala/Fifo.scala:46:20]     (CIRCT wrapInAtSquareBracket)
      - // src/main/scala/Fifo.scala:46:20      (CIRCT plain comment)
    """
    with open(verilog_file, 'r') as f:
        for line in f:
            if re.search(rf'\b(wire|reg)\b.*\b{re.escape(signal_name)}\b', line) and '//' in line:
                loc = _extract_location(line)
                if loc:
                    return loc
            if re.search(rf'\bassign\b\s+{re.escape(signal_name)}\b', line) and '//' in line:
                loc = _extract_location(line)
                if loc:
                    return loc
    return None


def _extract_location(line):
    """Extract source location from a Verilog comment line.

    Supports:
      // @[src/main/scala/Fifo.scala:46:20]
      // src/main/scala/Fifo.scala:46:20
    """
    # Try @[...] format first
    match = re.search(r'@\[([^\]]+)\]', line)
    if match:
        return match.group(1)
    # Try plain comment format: // <path>:<line>:<col>
    match = re.search(r'//\s*(.+\.scala:\d+.*)$', line)
    if match:
        return match.group(1).strip()
    return None


def get_expression_text(verilog_file, line_num, start_col, end_col):
    """Extract the expression text from a Verilog file at the given location."""
    with open(verilog_file, 'r') as f:
        for i, line in enumerate(f, 1):
            if i == line_num:
                # Columns are 1-indexed in Yosys src attributes
                return line[start_col - 1:end_col].rstrip()
    return None


def parse_loc(loc_str):
    """Parse location string like '21.23-39' into (line, start_col, end_col)."""
    match = re.match(r'(\d+)\.(\d+)-(\d+)$', loc_str)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def generate_miter_script(gold_file, gate_file, module_name):
    """Generate the Yosys miter setup commands."""
    gold_others = get_other_modules(gold_file, module_name)
    gate_others = get_other_modules(gate_file, module_name)

    gold_abs = os.path.abspath(gold_file)
    gate_abs = os.path.abspath(gate_file)

    gold_delete = '\n'.join(f'delete {m}' for m in gold_others)
    gate_delete = '\n'.join(f'delete {m}' for m in gate_others)

    return f"""read_verilog -formal {gold_abs}
{gold_delete}
prep -flatten -top {module_name}
rename -top gold
clk2fflogic
design -stash gold

read_verilog -formal {gate_abs}
{gate_delete}
prep -flatten -top {module_name}
rename -top gate
clk2fflogic

design -copy-from gold -as gold gold
miter -equiv -flatten -make_outputs gold gate miter
hierarchy -top miter
"""


def run_yosys_dump(gold_file, gate_file, module_name):
    """Run Yosys to create miter and dump RTLIL. Returns dump text."""
    script = generate_miter_script(gold_file, gate_file, module_name)
    script += "dump miter\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ys', delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            ['yosys', '-Q', '-s', script_path],
            capture_output=True, text=True, timeout=120
        )
        return result.stdout
    finally:
        os.unlink(script_path)


def parse_dump(dump_text, gate_file, gold_file):
    """Parse RTLIL dump to extract wire info.

    Returns:
        gate_wires: list of (wire_name, width, src_attr, hdlname)
        gold_wires: list of (wire_name, width, src_attr, hdlname)
    """
    gate_wires = []
    gold_wires = []

    gate_abs = os.path.abspath(gate_file)
    gold_abs = os.path.abspath(gold_file)

    # Parse state machine: collect attributes, then match wire declaration
    current_src = None
    current_hdlname = None

    for line in dump_text.split('\n'):
        line = line.strip()

        # Track attributes
        src_match = re.match(r'attribute\s+\\src\s+"([^"]+)"', line)
        if src_match:
            current_src = src_match.group(1)
            continue

        hdl_match = re.match(r'attribute\s+\\hdlname\s+"([^"]+)"', line)
        if hdl_match:
            current_hdlname = hdl_match.group(1)
            continue

        # Match wire declarations
        wire_match = re.match(r'wire\s+(?:width\s+(\d+)\s+)?(?:(?:input|output)\s+\d+\s+)?(.+)', line)
        if wire_match:
            width = int(wire_match.group(1)) if wire_match.group(1) else 1
            wire_name = wire_match.group(2).strip()

            # Classify as gold or gate
            if current_hdlname and current_hdlname.startswith('gold '):
                orig_name = current_hdlname[5:]  # strip "gold " prefix
                gold_wires.append((wire_name, width, current_src, orig_name))
            elif current_hdlname and current_hdlname.startswith('gate '):
                orig_name = current_hdlname[5:]  # strip "gate " prefix
                gate_wires.append((wire_name, width, current_src, orig_name))
            elif current_src:
                # No hdlname — check if src points to gold or gate file
                if gold_abs in (current_src or ''):
                    gold_wires.append((wire_name, width, current_src, None))
                elif gate_abs in (current_src or ''):
                    gate_wires.append((wire_name, width, current_src, None))

            # Reset attributes
            current_src = None
            current_hdlname = None
            continue

        # Non-wire/attribute lines reset attributes
        if not line.startswith('attribute'):
            current_src = None
            current_hdlname = None

    return gate_wires, gold_wires


def find_gate_target(gate_wires, gate_file, line, start_col, end_col):
    """Find the gate wire matching the given source location."""
    gate_abs = os.path.abspath(gate_file)

    # Build the src pattern to match: "<path>:<line>.<start_col>-<line>.<end_col>"
    target_src = f"{gate_abs}:{line}.{start_col}-{line}.{end_col}"

    matches = []
    for wire_name, width, src, hdlname in gate_wires:
        if src and target_src in src:
            matches.append((wire_name, width, src, hdlname))

    return matches


def filter_gold_candidates(gold_wires):
    """Filter gold wires to meaningful candidates (skip io ports, clock, reset, internals)."""
    candidates = []
    for wire_name, width, src, orig_name in gold_wires:
        # Skip if no original name and no useful src
        name = orig_name or wire_name

        # Skip clock, reset, io ports
        if orig_name:
            if orig_name in ('clock', 'reset'):
                continue
            if orig_name.startswith('io_'):
                continue

        # Skip clk2fflogic internals
        if 'clk2fflogic' in wire_name:
            continue
        # Skip miter infrastructure
        if wire_name.startswith('\\in_') or wire_name.startswith('\\trigger'):
            continue
        if wire_name.startswith('\\gold_') or wire_name.startswith('\\gate_'):
            continue
        # Skip procmux internals
        if '$procmux$' in wire_name:
            continue
        # Skip rtlil internals
        if 'rtlil.cc' in wire_name:
            continue
        # Skip $0\ next-state wires
        if '$0\\' in wire_name:
            continue

        candidates.append((wire_name, width, src, orig_name))

    return candidates


def run_proofs(gold_file, gate_file, module_name, gate_target_wire, candidates, bounded=False):
    """Generate and run proof script. Returns list of (candidate, passed)."""
    script = generate_miter_script(gold_file, gate_file, module_name)

    # Add one sat command per candidate
    for wire_name, width, src, orig_name in candidates:
        if bounded:
            script += f"sat -prove {wire_name} {gate_target_wire} -set-init-zero -seq 2\n"
        else:
            script += f"sat -tempinduct -prove trigger 0 -prove {wire_name} {gate_target_wire} -set-init-zero -seq 2 miter\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ys', delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        result = subprocess.run(
            ['yosys', '-Q', '-s', script_path],
            capture_output=True, text=True, timeout=600
        )
        output = result.stdout + result.stderr
    finally:
        os.unlink(script_path)

    # Parse SUCCESS/FAIL results in order
    results = []
    result_idx = 0
    for line in output.split('\n'):
        if 'SUCCESS!' in line:
            if result_idx < len(candidates):
                results.append((candidates[result_idx], True))
                result_idx += 1
        elif 'FAIL!' in line:
            if result_idx < len(candidates):
                results.append((candidates[result_idx], False))
                result_idx += 1

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Trace optimized Verilog signals back to Chisel source via formal equivalence',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 21.23-39
  python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 19.14-20 --bounded
  python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 21.23-39 --module DoubleBuffer
        """
    )

    parser.add_argument('--gold', '-g', required=True,
                        help='Path to gold (unoptimized) Verilog file')
    parser.add_argument('--gate', '-G', required=True,
                        help='Path to gate (optimized) Verilog file')
    parser.add_argument('--loc', '-l', required=True,
                        help='Signal location in gate file: <line>.<startcol>-<endcol> (e.g., 21.23-39)')
    parser.add_argument('--module', '-m',
                        help='Module name to check (auto-detected if not specified)')
    parser.add_argument('--bounded', '-b', action='store_true',
                        help='Use bounded BMC (default: unbounded k-induction)')

    args = parser.parse_args()

    # Parse location
    loc = parse_loc(args.loc)
    if not loc:
        print(f"Error: Invalid location format '{args.loc}'. Expected: <line>.<startcol>-<endcol> (e.g., 21.23-39)")
        sys.exit(1)
    line_num, start_col, end_col = loc

    # Verify files exist
    gold_file = str(Path(args.gold))
    gate_file = str(Path(args.gate))
    if not Path(gold_file).exists():
        print(f"Error: Gold file not found: {gold_file}")
        sys.exit(1)
    if not Path(gate_file).exists():
        print(f"Error: Gate file not found: {gate_file}")
        sys.exit(1)

    # Determine module name
    module_name = args.module
    if not module_name:
        module_name = detect_module_name(gold_file)
        if not module_name:
            print("Error: Could not auto-detect module name. Please specify with --module")
            sys.exit(1)

    # Get expression text from gate file
    expr_text = get_expression_text(gate_file, line_num, start_col, end_col)

    print("=" * 70)
    print("Signal Correspondence Tracer")
    print("=" * 70)
    print(f"\n  Gold (unoptimized): {gold_file}")
    print(f"  Gate (optimized):   {gate_file}")
    print(f"  Module:             {module_name}")
    print(f"  Target location:    {args.loc}")
    if expr_text:
        print(f"  Expression:         {expr_text}")
    print(f"  Proof method:       {'bounded BMC (-seq 2)' if args.bounded else 'unbounded k-induction (-tempinduct)'}")

    # Step 1: Run Yosys dump
    print(f"\n[Step 1] Creating miter circuit and dumping RTLIL...")
    dump_text = run_yosys_dump(gold_file, gate_file, module_name)

    # Step 2: Parse dump
    print("[Step 2] Parsing wire names from dump...")
    gate_wires, gold_wires = parse_dump(dump_text, gate_file, gold_file)

    # Step 3: Find gate target
    print(f"[Step 3] Finding gate signal at {args.loc}...")
    matches = find_gate_target(gate_wires, gate_file, line_num, start_col, end_col)

    if not matches:
        print(f"\n  Error: No signal found at location {args.loc}")
        print(f"  Available gate signals:")
        for wire_name, width, src, hdlname in gate_wires:
            if src and hdlname:
                # Extract line.col from src
                src_short = src.split(':')[-1] if ':' in src else src
                print(f"    {hdlname:<25} width={width}  src={src_short}")
            elif src:
                src_short = src.split(':')[-1] if ':' in src else src
                wire_short = wire_name.replace('\\', '')
                print(f"    {wire_short:<25} width={width}  src={src_short}")
        sys.exit(1)

    gate_target_wire, gate_target_width, gate_target_src, gate_target_hdl = matches[0]
    print(f"  Found: {gate_target_wire}")
    print(f"  Width: {gate_target_width}")
    if gate_target_hdl:
        print(f"  HDL name: {gate_target_hdl}")

    # Step 4: Filter gold candidates
    print(f"\n[Step 4] Collecting gold candidates (width={gate_target_width})...")
    candidates = filter_gold_candidates(gold_wires)
    candidates = [(w, wd, s, h) for w, wd, s, h in candidates if wd == gate_target_width]

    print(f"  Found {len(candidates)} candidates with matching width:")
    for wire_name, width, src, orig_name in candidates:
        display_name = orig_name or wire_name.replace('\\', '')
        print(f"    {display_name}")

    if not candidates:
        print("\n  No candidates with matching width found.")
        sys.exit(1)

    # Step 5: Run proofs
    print(f"\n[Step 5] Running formal proofs ({len(candidates)} candidates)...")
    results = run_proofs(gold_file, gate_file, module_name, gate_target_wire, candidates, args.bounded)

    # Step 6: Extract Chisel source and report
    equivalent = [(cand, passed) for cand, passed in results if passed]

    print(f"\n{'=' * 70}")
    print(f"Results")
    print(f"{'=' * 70}")

    if expr_text:
        print(f"\n  Target: {gate_file}:{line_num}.{start_col}-{end_col} ({expr_text})")
    else:
        print(f"\n  Target: {gate_file}:{line_num}.{start_col}-{end_col}")
    print(f"  Yosys wire: {gate_target_wire}")

    if equivalent:
        print(f"\n  Equivalent signals in {gold_file}:\n")
        print(f"  {'Signal':<25} {'Width':<6} {'Chisel Source'}")
        print(f"  {'─' * 25} {'─' * 5} {'─' * 40}")

        for (wire_name, width, src, orig_name), _ in equivalent:
            display_name = orig_name or wire_name.replace('\\', '')
            loc_info = get_source_location(display_name, gold_file)
            if loc_info:
                # Shorten path
                loc_short = loc_info.split('/')[-1] if '/' in loc_info else loc_info
            else:
                loc_short = "N/A"
            print(f"  {display_name:<25} {width:<6} {loc_short}")
    else:
        print("\n  No equivalent signals found.")

    # Summary
    total = len(results)
    passed = len(equivalent)
    failed = total - passed
    print(f"\n  Proved: {passed}/{total} equivalent, {failed} not equivalent")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
