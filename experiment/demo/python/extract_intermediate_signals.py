#!/usr/bin/env python3
"""
Extract intermediate signal names from Yosys analysis of a SystemVerilog file.
"""
import subprocess
import sys

def get_intermediate_signals(sv_file, top_module):
    """
    Use Yosys to read a SystemVerilog file and extract intermediate signal names.

    Args:
        sv_file: Path to the SystemVerilog file
        top_module: Name of the top module

    Returns:
        List of (signal_name, is_intermediate) tuples
    """
    yosys_script = f"""
read_verilog -sv {sv_file}
hierarchy -check -top {top_module}
proc; opt
cd {top_module}
select w:*
select -list
"""

    # Run Yosys
    result = subprocess.run(
        ['yosys', '-Q'],
        input=yosys_script,
        capture_output=True,
        text=True
    )

    # Parse output
    all_signals = []
    intermediate_signals = []

    for line in result.stdout.split('\n'):
        line = line.strip()
        if line.startswith(f"{top_module}/"):
            signal_name = line.split('/')[-1]
            all_signals.append(signal_name)

            # Intermediate signals are those with $ in their name (Yosys-generated)
            if '$' in signal_name:
                intermediate_signals.append(signal_name)

    return all_signals, intermediate_signals

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_intermediate_signals.py <sv_file> [top_module]")
        sys.exit(1)

    sv_file = sys.argv[1]
    top_module = sys.argv[2] if len(sys.argv) > 2 else None

    # Auto-detect top module if not provided
    if not top_module:
        # Simple heuristic: look for "module" declaration
        with open(sv_file, 'r') as f:
            for line in f:
                if line.strip().startswith('module '):
                    top_module = line.split()[1].split('(')[0]
                    break

    all_signals, intermediate_signals = get_intermediate_signals(sv_file, top_module)

    print(f"Top module: {top_module}")
    print(f"\n=== ALL SIGNALS ({len(all_signals)}) ===")
    for sig in all_signals:
        print(f"  {sig}")

    print(f"\n=== INTERMEDIATE SIGNALS ({len(intermediate_signals)}) ===")
    for sig in intermediate_signals:
        print(f"  {sig}")
