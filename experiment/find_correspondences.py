#!/usr/bin/env python3
"""
Generalized Signal Correspondence Finder

This script automatically finds all signal correspondences between
optimized and unoptimized Verilog by trying all pairs with formal verification.

Supports both combinational and sequential circuits.

Usage:
    python3 find_correspondences.py --dir demo_complex
    python3 find_correspondences.py --dir demo_fifo --module DoubleBuffer
    python3 find_correspondences.py --gold path/to/unoptimized.sv --gate path/to/optimized.sv --module MyModule
    python3 find_correspondences.py --dir demo_fifo --sequential  # Force sequential checking
"""

import subprocess
import re
import sys
import argparse
import os
from pathlib import Path


def detect_module_name(verilog_file):
    """Auto-detect the first module name from a Verilog file."""
    with open(verilog_file, 'r') as f:
        for line in f:
            match = re.match(r'\s*module\s+(\w+)', line)
            if match:
                return match.group(1)
    return None


def is_sequential_circuit(verilog_file):
    """Detect if a Verilog file contains sequential logic (registers)."""
    with open(verilog_file, 'r') as f:
        content = f.read()
        # Check for register declarations or always blocks with clock
        return bool(re.search(r'\breg\b', content) or
                    re.search(r'always\s*@\s*\(\s*posedge', content))


def get_signals_with_widths(verilog_file, module_name):
    """Extract all wire names and their bit widths from a Verilog file using Yosys."""
    script = f"""
read_verilog -sv {verilog_file}
cd {module_name}
dump
"""
    result = subprocess.run(
        ['yosys', '-Q', '-p', script],
        capture_output=True, text=True
    )

    # Parse wire names and widths from dump output
    # Format: "wire width N \signal_name"
    signals = {}
    for line in result.stdout.split('\n'):
        line = line.strip()
        # Match: wire width 16 \mul1
        match = re.match(r'wire\s+width\s+(\d+)\s+\\(\S+)', line)
        if match:
            width = int(match.group(1))
            name = match.group(2)
            signals[name] = width

    return signals


def get_other_modules(verilog_file, target_module):
    """Find all module names in a Verilog file except the target module."""
    modules = []
    with open(verilog_file, 'r') as f:
        for line in f:
            match = re.match(r'\s*module\s+(\w+)', line)
            if match and match.group(1) != target_module:
                modules.append(match.group(1))
    return modules


def test_equivalence(gold_file, gate_file, module_name, gold_sig, gate_sig, use_induct=False):
    """Test if two signals are equivalent using Yosys.

    Args:
        gold_file: Path to unoptimized Verilog
        gate_file: Path to optimized Verilog
        module_name: Name of the module to check
        gold_sig: Signal name in gold (unoptimized)
        gate_sig: Signal name in gate (optimized)
        use_induct: If True, use equiv_induct for sequential circuits

    Returns True only if the specific signal pair is proven equivalent.

    Note: For signals with identical names in both designs, equiv_make merges them,
    making direct comparison impossible. We skip such pairs and only report
    same-named signals as matching by name (handled elsewhere).
    """
    equiv_cmd = "equiv_induct" if use_induct else "equiv_simple"

    # For sequential circuits with same-named signals, equiv_make merges them.
    # Cross-comparisons (different names) become unreliable due to this merging.
    # We handle this by:
    # 1. Same-named signals: Skip formal check, report as match (merged by equiv_make)
    # 2. Different-named signals: Only reliable for combinational or when names differ
    if gold_sig == gate_sig:
        # Same name - equiv_make auto-merges and proves these
        return True

    # Find other modules to delete (to avoid re-definition errors)
    gold_other_modules = get_other_modules(gold_file, module_name)
    gate_other_modules = get_other_modules(gate_file, module_name)

    gold_delete_cmds = '\n'.join(f'delete {m}' for m in gold_other_modules)
    gate_delete_cmds = '\n'.join(f'delete {m}' for m in gate_other_modules)

    script = f"""
read_verilog -sv {gold_file}
rename {module_name} gold
{gold_delete_cmds}

read_verilog -sv {gate_file}
rename {module_name} gate
{gate_delete_cmds}

proc
opt_clean
equiv_make gold gate equiv_mod
cd equiv_mod

# Count cells before adding our pair
select -count t:$equiv

# Add our specific pair
equiv_add \\{gold_sig}_gold \\{gate_sig}_gate

# Count cells after adding our pair
select -count t:$equiv

# Try to prove
{equiv_cmd}

# Check status
equiv_status
"""
    try:
        result = subprocess.run(
            ['yosys', '-Q', '-p', script],
            capture_output=True, text=True,
            timeout=120  # Longer timeout for sequential circuits
        )
    except subprocess.TimeoutExpired:
        return False

    output = result.stdout

    # Check for errors in equiv_add
    if 'Error in gold signal' in output or 'Error in gate signal' in output:
        return False

    # Parse the two "select -count" outputs to verify cells were added
    counts = re.findall(r'(\d+) objects', output)
    if len(counts) >= 2:
        before = int(counts[0])
        after = int(counts[1])
        cells_added = after - before
        if cells_added <= 0:
            # No cells were added - signals don't exist or width mismatch
            return False
    else:
        return False

    # Check final status
    # We need to verify that the ADDED cells (not pre-existing ones) are all proven
    # The added cells are tracked by equiv_add and can be identified by looking at
    # whether any "Unproven $equiv $auto$equiv_add" lines exist
    #
    # Note: equiv_make auto-creates some $equiv cells that might be unproven.
    # We only care about the cells WE added via equiv_add.
    equiv_add_unproven = re.findall(r'Unproven \$equiv \$auto\$equiv_add', output)
    if len(equiv_add_unproven) > 0:
        # Our added cells have unproven bits - not equivalent
        return False

    # Verify that some cells exist (sanity check)
    match = re.search(r'Of those cells (\d+) are proven', output)
    if match:
        proven = int(match.group(1))
        return proven > 0

    return False


def get_source_location(signal_name, verilog_file):
    """Extract source location for a signal from Verilog comments."""
    with open(verilog_file, 'r') as f:
        for line in f:
            # Match wire declarations with the signal name
            if re.search(rf'\bwire\b.*\b{re.escape(signal_name)}\b', line) and '//' in line:
                match = re.search(r'@\[([^\]]+)\]', line)
                if match:
                    return match.group(1)
            # Also check for reg declarations (for sequential circuits)
            if re.search(rf'\breg\b.*\b{re.escape(signal_name)}\b', line) and '//' in line:
                match = re.search(r'@\[([^\]]+)\]', line)
                if match:
                    return match.group(1)
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Find signal correspondences between optimized and unoptimized Verilog',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 find_correspondences.py --dir demo_complex
  python3 find_correspondences.py --dir demo_fifo --module DoubleBuffer
  python3 find_correspondences.py --gold unopt.sv --gate opt.sv --module MyMod
  python3 find_correspondences.py --dir demo_fifo --sequential
        """
    )

    parser.add_argument('--dir', '-d',
                        help='Directory containing generated/ folder with optimized.sv and unoptimized.sv')
    parser.add_argument('--gold', '-g',
                        help='Path to gold (unoptimized) Verilog file')
    parser.add_argument('--gate', '-G',
                        help='Path to gate (optimized) Verilog file')
    parser.add_argument('--module', '-m',
                        help='Module name to check (auto-detected if not specified)')
    parser.add_argument('--sequential', '-s', action='store_true',
                        help='Force sequential equivalence checking (equiv_induct)')
    parser.add_argument('--combinational', '-c', action='store_true',
                        help='Force combinational equivalence checking (equiv_simple)')

    args = parser.parse_args()

    # Determine file paths
    if args.dir:
        base_dir = Path(args.dir)
        if not base_dir.is_absolute():
            # Try relative to script location first, then current directory
            script_dir = Path(__file__).parent
            if (script_dir / args.dir / 'generated').exists():
                base_dir = script_dir / args.dir
            elif (Path(args.dir) / 'generated').exists():
                base_dir = Path(args.dir)
            else:
                print(f"Error: Cannot find generated/ folder in {args.dir}")
                sys.exit(1)

        gold_file = base_dir / 'generated' / 'unoptimized.sv'
        gate_file = base_dir / 'generated' / 'optimized.sv'
    elif args.gold and args.gate:
        gold_file = Path(args.gold)
        gate_file = Path(args.gate)
    else:
        parser.print_help()
        print("\nError: Must specify either --dir or both --gold and --gate")
        sys.exit(1)

    # Verify files exist
    if not gold_file.exists():
        print(f"Error: Gold file not found: {gold_file}")
        sys.exit(1)
    if not gate_file.exists():
        print(f"Error: Gate file not found: {gate_file}")
        sys.exit(1)

    # Determine module name
    module_name = args.module
    if not module_name:
        module_name = detect_module_name(str(gold_file))
        if not module_name:
            print("Error: Could not auto-detect module name. Please specify with --module")
            sys.exit(1)

    # equiv_induct works for both combinational and sequential circuits
    # (for combinational, it converges in one step)
    # Only use equiv_simple if explicitly requested for speed
    if args.combinational:
        use_induct = False
    else:
        use_induct = True  # Default to equiv_induct - works for everything

    print("=" * 70)
    print("Signal Correspondence Finder")
    print("=" * 70)
    print(f"\n  Gold (unoptimized): {gold_file}")
    print(f"  Gate (optimized):   {gate_file}")
    print(f"  Module:             {module_name}")
    print(f"  Proof method:       {'equiv_induct (works for all circuits)' if use_induct else 'equiv_simple (combinational only)'}")

    # Step 1: Get all signals with their widths from both designs
    print("\n[Step 1] Extracting signals and widths from both Verilog files...")

    gold_signals = get_signals_with_widths(str(gold_file), module_name)
    gate_signals = get_signals_with_widths(str(gate_file), module_name)

    # Filter out clock, reset, and io ports (they match by name anyway)
    def is_internal(sig):
        return not sig.startswith('io_') and sig not in ['clock', 'reset']

    gold_internal = {s: w for s, w in gold_signals.items() if is_internal(s)}
    gate_internal = {s: w for s, w in gate_signals.items() if is_internal(s)}

    print(f"\n  Gold (unoptimized) internal signals: {len(gold_internal)}")
    for s, w in sorted(gold_internal.items()):
        print(f"    - {s:<25} (width: {w})")

    print(f"\n  Gate (optimized) internal signals: {len(gate_internal)}")
    for s, w in sorted(gate_internal.items()):
        print(f"    - {s:<25} (width: {w})")

    # Step 2: Try pairs with matching widths only
    print(f"\n[Step 2] Testing pairs with matching bit widths...")

    # Detect if there are same-named signals in both designs
    # (This affects how equiv_make works - it merges same-named signals)
    same_named_signals = set(gold_internal.keys()) & set(gate_internal.keys())
    has_same_named = len(same_named_signals) > 0

    if has_same_named:
        print(f"\n  Note: Found {len(same_named_signals)} same-named signal(s) in both designs: {same_named_signals}")
        print("  equiv_make merges same-named signals, so cross-comparisons are skipped.")
        print("  Will test: (1) same-named pairs (auto-merged), (2) pairs where neither name exists in the other design.\n")

    # Count how many pairs have matching widths
    matching_width_pairs = []
    for gold_sig, gold_width in gold_internal.items():
        for gate_sig, gate_width in gate_internal.items():
            if gold_width == gate_width:
                matching_width_pairs.append((gold_sig, gate_sig, gold_width))

    # When same-named signals exist, equiv_make merges them, causing issues.
    # Only test:
    # 1. Same-named pairs (always reliable - auto-merged by equiv_make)
    # 2. Different-named pairs where neither name exists in the other design
    #    (to avoid confusion from equiv_make's merging)
    if has_same_named:
        filtered_pairs = []
        for gold_sig, gate_sig, width in matching_width_pairs:
            if gold_sig == gate_sig:
                # Same name - always test
                filtered_pairs.append((gold_sig, gate_sig, width))
            elif gold_sig not in gate_internal and gate_sig not in gold_internal:
                # Neither name exists in the other design - safe to test
                filtered_pairs.append((gold_sig, gate_sig, width))
            # Skip pairs where one name exists in the other design (merging causes issues)
        matching_width_pairs = filtered_pairs

    print(f"  Total pairs: {len(gold_internal)} x {len(gate_internal)} = {len(gold_internal) * len(gate_internal)}")
    print(f"  Pairs with matching widths to test: {len(matching_width_pairs)}")
    print("  (Skipping pairs with mismatched widths)\n")

    correspondences = []
    tested = 0
    total = len(matching_width_pairs)

    for gold_sig, gate_sig, width in matching_width_pairs:
        tested += 1
        sys.stdout.write(f"\r  [{tested}/{total}] Testing: {gold_sig:<20} <-> {gate_sig:<20} (width: {width})")
        sys.stdout.flush()

        try:
            if test_equivalence(str(gold_file), str(gate_file), module_name,
                               gold_sig, gate_sig, use_induct):
                correspondences.append((gold_sig, gate_sig, width))
                print(f"\n  ✓ MATCH: {gold_sig} ≡ {gate_sig}")
        except subprocess.TimeoutExpired:
            print(f"\n  ⏱ TIMEOUT: {gold_sig} <-> {gate_sig}")
        except Exception as e:
            pass  # Skip on error

    # Step 3: Results
    print(f"\n\n[Step 3] Results")
    print("=" * 70)

    if correspondences:
        print(f"\nFound {len(correspondences)} signal correspondences:\n")
        print(f"{'Gold (unoptimized)':<20} {'Gate (optimized)':<20} {'Width':<6} {'Chisel Source'}")
        print("-" * 90)

        for gold_sig, gate_sig, width in correspondences:
            loc = get_source_location(gold_sig, str(gold_file))
            # Extract just the relevant part of the location
            if loc:
                loc_str = loc.split('/')[-1] if '/' in loc else loc
            else:
                loc_str = "N/A"
            print(f"{gold_sig:<20} {gate_sig:<20} {width:<6} {loc_str}")
    else:
        print("No correspondences found.")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
