#!/usr/bin/env python3
"""
Formal Signal Correspondence Tracing using Yosys

This script uses Yosys's equivalence checking to formally prove which signals
in the optimized Verilog correspond to which signals in the unoptimized version.

Key features:
- Uses equiv_induct for sequential circuits (with registers)
- Uses equiv_simple for combinational logic
- Automatically matches signals by port names via equiv_make
- Can discover cross-signal equivalences (e.g., opt._GEN_0 == unopt._GEN_4)
"""

import subprocess
import re
import sys
import os
import tempfile
from typing import List, Tuple, Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class Signal:
    name: str
    width: int
    line_num: int
    chisel_loc: str
    expression: str


@dataclass
class EquivResult:
    gold_signal: str
    gate_signal: str
    is_equivalent: bool
    chisel_loc: str = ""


class Colors:
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    ENDC = '\033[0m'


def extract_module_to_temp(filepath: str, module_name: str, new_name: str, temp_dir: str) -> str:
    """
    Extract a single module from a Verilog file and save with new name.
    """
    with open(filepath, 'r') as f:
        content = f.read()

    pattern = rf'(module\s+{module_name}\s*\(.*?endmodule)'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return ""

    module_content = match.group(1)
    module_content = re.sub(
        rf'module\s+{module_name}',
        f'module {new_name}',
        module_content,
        count=1
    )

    temp_file = os.path.join(temp_dir, f'{new_name}.sv')
    with open(temp_file, 'w') as f:
        f.write(module_content)

    return temp_file


def run_equiv_check_all(gold_file: str, gate_file: str, verbose: bool = False) -> List[EquivResult]:
    """
    Run Yosys equivalence checking and return all proven equivalences.
    Uses equiv_induct for sequential circuits and equiv_simple for combinational.
    """
    yosys_script = f"""
read_verilog -sv {gold_file}
read_verilog -sv {gate_file}

proc
opt_clean

equiv_make gold gate equiv_mod
cd equiv_mod

# Use induction for sequential circuits (handles registers)
equiv_induct

# Then simple SAT for remaining combinational logic
equiv_simple

# Get detailed status
equiv_status
"""

    try:
        result = subprocess.run(
            ['yosys', '-Q'],
            input=yosys_script,
            capture_output=True,
            text=True,
            timeout=120
        )

        output = result.stdout + result.stderr

        if verbose:
            # Print last part of output for debugging
            lines = output.strip().split('\n')
            print("\n  Yosys output (last 30 lines):")
            for line in lines[-30:]:
                print(f"    {line}")

        # Parse proven equivalences from output
        results = []

        # Look for lines like:
        # "  Trying to prove $equiv for \signal_name [bit]: success!"
        # And from equiv_status output like:
        # "  Of those cells N are proven and M are unproven."

        # Parse proven signals from "success!" messages
        success_pattern = r"Trying to prove \$equiv for \\(\w+)(?:\s*\[(\d+)\])?: success!"
        for match in re.finditer(success_pattern, output):
            signal = match.group(1)
            # Remove _gold or _gate suffix if present to get base name
            if signal.endswith('_gold'):
                signal = signal[:-5]
            elif signal.endswith('_gate'):
                signal = signal[:-5]

            # Avoid duplicates
            if not any(r.gold_signal == signal for r in results):
                results.append(EquivResult(
                    gold_signal=signal,
                    gate_signal=signal,
                    is_equivalent=True
                ))

        # Also look at the equiv_status summary to find auto-matched signals
        # Pattern: Found N $equiv cells in equiv_mod:
        #          Of those cells X are proven and Y are unproven.
        proven_match = re.search(r'Of those cells (\d+) are proven', output)
        if proven_match:
            proven_count = int(proven_match.group(1))
            if verbose:
                print(f"\n  Total proven equiv cells: {proven_count}")

        return results

    except subprocess.TimeoutExpired:
        print(f"{Colors.YELLOW}Timeout during equivalence checking{Colors.ENDC}")
        return []
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.ENDC}")
        return []


def discover_cross_equivalences(
    gold_file: str,
    gate_file: str,
    gold_signals: List[str],
    gate_signals: List[str],
    verbose: bool = False
) -> List[EquivResult]:
    """
    Discover equivalences between differently-named signals.
    For each gate signal, try to find an equivalent gold signal.
    """
    results = []

    # Filter out Yosys internal signals and ports
    gate_candidates = [s for s in gate_signals
                       if not s.startswith('$') and s not in ['clock', 'reset']]
    gold_candidates = [s for s in gold_signals
                       if not s.startswith('$') and s not in ['clock', 'reset']]

    if verbose:
        print(f"\n{Colors.CYAN}Discovering cross-signal equivalences...{Colors.ENDC}")
        print(f"  Testing {len(gate_candidates)} optimized signals against {len(gold_candidates)} unoptimized signals")

    total = len(gate_candidates)
    for idx, gate_sig in enumerate(gate_candidates):
        if verbose:
            print(f"\r  Progress: {idx+1}/{total} - {gate_sig[:25]:<25}", end="", flush=True)

        for gold_sig in gold_candidates:
            # Skip if same name (already handled by equiv_make)
            if gate_sig == gold_sig:
                continue

            # Try to prove equivalence
            is_equiv = check_single_cross_equiv(gold_file, gate_file, gold_sig, gate_sig)

            if is_equiv:
                results.append(EquivResult(
                    gold_signal=gold_sig,
                    gate_signal=gate_sig,
                    is_equivalent=True
                ))

    if verbose:
        print(f"\r  Progress: {total}/{total} - Done!                    ")
        print(f"  Found {len(results)} cross-signal equivalences")

    return results


def check_single_cross_equiv(
    gold_file: str,
    gate_file: str,
    gold_signal: str,
    gate_signal: str
) -> bool:
    """
    Check if two differently-named signals are equivalent.
    """
    yosys_script = f"""
read_verilog -sv {gold_file}
read_verilog -sv {gate_file}

proc
opt_clean

equiv_make gold gate equiv_mod
cd equiv_mod

equiv_add -try \\{gold_signal}_gold \\{gate_signal}_gate

equiv_induct
equiv_simple
equiv_status -assert
"""

    try:
        result = subprocess.run(
            ['yosys', '-Q', '-q'],
            input=yosys_script,
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check return code - 0 means all equiv cells proven
        return result.returncode == 0

    except:
        return False


def get_signals_from_yosys(temp_file: str, module_name: str) -> List[str]:
    """
    Use Yosys to get all wire names from a module after elaboration.
    """
    yosys_script = f"""
read_verilog -sv {temp_file}
hierarchy -top {module_name}
proc
opt_clean
cd {module_name}
select -list w:*
"""
    try:
        result = subprocess.run(
            ['yosys', '-Q'],
            input=yosys_script,
            capture_output=True,
            text=True,
            timeout=30
        )

        signals = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith(f'{module_name}/'):
                sig_name = line.split('/')[-1]
                signals.append(sig_name)

        return signals
    except Exception as e:
        print(f"Error: {e}")
        return []


def extract_signals_from_verilog(filepath: str, module_name: str) -> List[Signal]:
    """
    Extract all wire/reg signals with their definitions from a Verilog file.
    """
    signals = []
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()

        in_target_module = False
        for i, line in enumerate(lines, 1):
            if f'module {module_name}' in line:
                in_target_module = True
                continue
            if in_target_module and 'endmodule' in line:
                break

            if not in_target_module:
                continue

            chisel_loc = ""
            loc_match = re.search(r'@\[([^\]]+)\]', line)
            if loc_match:
                chisel_loc = loc_match.group(1)

            # wire [width] name = expression;
            wire_match = re.search(
                r'wire\s+(?:\[(\d+):(\d+)\])?\s*(\w+)\s*=\s*([^;]+);',
                line
            )
            if wire_match:
                name = wire_match.group(3)
                expr = wire_match.group(4).strip()
                signals.append(Signal(name, 1, i, chisel_loc, expr))
                continue

            # wire [width] name;
            wire_decl = re.search(r'wire\s+(?:\[(\d+):(\d+)\])?\s*(\w+)\s*;', line)
            if wire_decl:
                name = wire_decl.group(3)
                signals.append(Signal(name, 1, i, chisel_loc, "(wire)"))
                continue

            # reg [width] name;
            reg_match = re.search(r'reg\s+(?:\[(\d+):(\d+)\])?\s*(\w+)\s*;', line)
            if reg_match:
                name = reg_match.group(3)
                signals.append(Signal(name, 1, i, chisel_loc, "(register)"))
                continue

            # assign name = expression;
            assign_match = re.search(r'assign\s+(\w+)\s*=\s*([^;]+);', line)
            if assign_match:
                name = assign_match.group(1)
                expr = assign_match.group(2).strip()
                signals.append(Signal(name, 1, i, chisel_loc, expr))
                continue

            # input/output declarations
            io_match = re.search(r'(input|output)\s+(?:\[(\d+):(\d+)\])?\s*(\w+)', line)
            if io_match:
                name = io_match.group(4)
                signals.append(Signal(name, 1, i, chisel_loc, f"({io_match.group(1)})"))

    except Exception as e:
        print(f"Error: {e}")

    return signals


def extract_chisel_code(filepath: str, line_num: int) -> str:
    """Get code from Chisel source file."""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            if 1 <= line_num <= len(lines):
                code = lines[line_num - 1].strip()
                if len(code) > 42:
                    code = code[:39] + "..."
                return code
    except:
        pass
    return ""


def parse_chisel_location(loc_string: str) -> Optional[Tuple[str, int]]:
    """Parse Chisel file and line from location string."""
    if not loc_string:
        return None

    match = re.search(r'([^:]+\.scala):(\d+)', loc_string)
    if match:
        return match.group(1), int(match.group(2))
    return None


def print_results(
    same_name_results: List[EquivResult],
    cross_results: List[EquivResult],
    unopt_file: str,
    opt_file: str,
    module_name: str,
    chisel_base_path: str = "src/main/scala"
):
    """Print formatted results table."""

    # Get signal info for line numbers and Chisel locations
    unopt_signals = extract_signals_from_verilog(unopt_file, module_name)
    opt_signals = extract_signals_from_verilog(opt_file, module_name)

    unopt_lookup = {sig.name: sig for sig in unopt_signals}
    opt_lookup = {sig.name: sig for sig in opt_signals}

    widths = [28, 28, 40, 18]
    total_width = sum(widths) + 13
    separator = "═" * total_width

    print(f"\n{Colors.BOLD}{separator}{Colors.ENDC}")
    print(f"{Colors.BOLD}Formal Signal Correspondence (Yosys SAT + Induction){Colors.ENDC}")
    print(f"{Colors.BOLD}{separator}{Colors.ENDC}\n")

    headers = ["Optimized Signal", "≡ Unoptimized Signal", "Chisel Source", "Status"]
    header_line = " │ ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("─" * total_width)

    all_results = same_name_results + cross_results
    proven_count = 0

    # Sort by gate signal name
    for eq in sorted(all_results, key=lambda x: x.gate_signal):
        proven_count += 1

        # Column 1: Optimized signal
        col1 = eq.gate_signal
        if eq.gate_signal in opt_lookup:
            col1 += f"\n(line {opt_lookup[eq.gate_signal].line_num})"

        # Column 2: Unoptimized signal
        col2 = eq.gold_signal
        if eq.gold_signal in unopt_lookup:
            col2 += f"\n(line {unopt_lookup[eq.gold_signal].line_num})"

        # Column 3: Chisel source
        col3 = ""
        chisel_loc = ""
        if eq.gold_signal in unopt_lookup:
            chisel_loc = unopt_lookup[eq.gold_signal].chisel_loc
        elif eq.gate_signal in opt_lookup:
            chisel_loc = opt_lookup[eq.gate_signal].chisel_loc

        if chisel_loc:
            parsed = parse_chisel_location(chisel_loc)
            if parsed:
                filepath, line = parsed
                full_path = os.path.join(chisel_base_path, os.path.basename(filepath))
                code = extract_chisel_code(full_path, line)
                if code:
                    col3 = f"{code}\n(line {line})"

        # Column 4: Status
        if eq.gate_signal == eq.gold_signal:
            col4 = f"{Colors.GREEN}✓ PROVEN{Colors.ENDC}"
        else:
            col4 = f"{Colors.CYAN}✓ CROSS{Colors.ENDC}"

        print_multiline_row([col1, col2, col3, col4], widths)
        print("─" * total_width)

    # Summary
    same_count = len(same_name_results)
    cross_count = len(cross_results)
    print(f"\n{Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"  {Colors.GREEN}Same-name equivalences: {same_count}{Colors.ENDC}")
    print(f"  {Colors.CYAN}Cross-signal equivalences: {cross_count}{Colors.ENDC}")
    print(f"  Total proven: {proven_count}")
    print(separator)


def print_multiline_row(cells: List[str], widths: List[int]):
    """Print a table row that may have multiple lines."""
    cell_lines = [str(cell).split('\n') for cell in cells]
    max_lines = max(len(lines) for lines in cell_lines)

    for lines in cell_lines:
        while len(lines) < max_lines:
            lines.append("")

    for i in range(max_lines):
        row_parts = []
        for j, (lines, width) in enumerate(zip(cell_lines, widths)):
            text = lines[i]
            visible_len = len(re.sub(r'\033\[[0-9;]*m', '', text))
            padding = width - visible_len
            if padding > 0:
                text = text + " " * padding
            row_parts.append(text[:width + 20])
        print(" │ ".join(row_parts))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Formal signal correspondence tracing using Yosys (SAT + Induction)"
    )
    parser.add_argument("--unopt", "-u", default="generated/unoptimized.sv")
    parser.add_argument("--opt", "-o", default="generated/optimized.sv")
    parser.add_argument("--module", "-m", default="DoubleBuffer")
    parser.add_argument("--chisel-src", "-c", default="src/main/scala")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--cross", action="store_true",
                        help="Also discover cross-signal equivalences (slower)")

    args = parser.parse_args()

    print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}Formal Signal Correspondence Tracer{Colors.ENDC}")
    print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"\nUsing Yosys equivalence checking:")
    print(f"  - equiv_induct: for sequential circuits (registers)")
    print(f"  - equiv_simple: for combinational logic")
    print(f"  - SAT solving to prove functional equivalence\n")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract modules
        gold_file = extract_module_to_temp(args.unopt, args.module, 'gold', temp_dir)
        gate_file = extract_module_to_temp(args.opt, args.module, 'gate', temp_dir)

        if not gold_file or not gate_file:
            print(f"{Colors.RED}Error: Could not extract module {args.module}{Colors.ENDC}")
            return 1

        print(f"{Colors.CYAN}Running equivalence checking...{Colors.ENDC}")

        # Run main equivalence check
        same_name_results = run_equiv_check_all(gold_file, gate_file, verbose=args.verbose)

        cross_results = []
        if args.cross:
            # Get signal lists for cross-checking
            gold_signals = get_signals_from_yosys(gold_file, 'gold')
            gate_signals = get_signals_from_yosys(gate_file, 'gate')

            cross_results = discover_cross_equivalences(
                gold_file, gate_file,
                gold_signals, gate_signals,
                verbose=args.verbose
            )

        if not same_name_results and not cross_results:
            print(f"\n{Colors.YELLOW}No equivalences found.{Colors.ENDC}")
            return 1

        # Print results
        print_results(
            same_name_results,
            cross_results,
            args.unopt,
            args.opt,
            args.module,
            args.chisel_src
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
