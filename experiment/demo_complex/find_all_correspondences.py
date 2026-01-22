#!/usr/bin/env python3
"""
Automated Signal Correspondence Finder

This script automatically finds all signal correspondences between
optimized and unoptimized Verilog by trying all pairs with formal verification.
"""

import subprocess
import re
import sys

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

def test_equivalence(gold_sig, gate_sig):
    """Test if two signals are equivalent using Yosys.

    Returns True only if the specific signal pair is proven equivalent.
    """
    script = f"""
read_verilog -sv generated/unoptimized.sv
rename ComplexExample gold
read_verilog -sv generated/optimized.sv
rename ComplexExample gate

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
equiv_simple

# Check status
equiv_status
"""
    result = subprocess.run(
        ['yosys', '-Q', '-p', script],
        capture_output=True, text=True,
        timeout=60
    )

    output = result.stdout

    # Check for errors in equiv_add
    if 'Error in gold signal' in output or 'Error in gate signal' in output:
        return False

    # Parse the two "select -count" outputs to verify cells were added
    counts = re.findall(r'(\d+) objects', output)
    if len(counts) >= 2:
        before = int(counts[0])
        after = int(counts[1])
        if after <= before:
            # No cells were added - signals don't exist or width mismatch
            return False

    # Check final status - must have 0 unproven
    match = re.search(r'Of those cells (\d+) are proven and (\d+) are unproven', output)
    if match:
        proven = int(match.group(1))
        unproven = int(match.group(2))
        return unproven == 0 and proven > 0

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
    return None

def main():
    print("=" * 70)
    print("Automated Signal Correspondence Finder")
    print("=" * 70)

    # Step 1: Get all signals with their widths from both designs
    print("\n[Step 1] Extracting signals and widths from both Verilog files...")

    gold_signals = get_signals_with_widths('generated/unoptimized.sv', 'ComplexExample')
    gate_signals = get_signals_with_widths('generated/optimized.sv', 'ComplexExample')

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

    # Count how many pairs have matching widths
    matching_width_pairs = []
    for gold_sig, gold_width in gold_internal.items():
        for gate_sig, gate_width in gate_internal.items():
            if gold_width == gate_width:
                matching_width_pairs.append((gold_sig, gate_sig, gold_width))

    print(f"  Total pairs: {len(gold_internal)} x {len(gate_internal)} = {len(gold_internal) * len(gate_internal)}")
    print(f"  Pairs with matching widths: {len(matching_width_pairs)}")
    print("  (Skipping pairs with mismatched widths)\n")

    correspondences = []
    tested = 0
    total = len(matching_width_pairs)

    for gold_sig, gate_sig, width in matching_width_pairs:
        tested += 1
        sys.stdout.write(f"\r  [{tested}/{total}] Testing: {gold_sig:<20} <-> {gate_sig:<20} (width: {width})")
        sys.stdout.flush()

        try:
            if test_equivalence(gold_sig, gate_sig):
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
            loc = get_source_location(gold_sig, 'generated/unoptimized.sv')
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
