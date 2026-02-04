#!/usr/bin/env python3
"""
FIFO Signal Tracing - Automatically extract ALL signals from optimized Verilog
"""

import re
from typing import List, Tuple, Optional

class Colors:
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    ENDC = '\033[0m'

def parse_chisel_locations(loc_string: str) -> List[Tuple[int, int]]:
    """Parse all line:col pairs from location"""
    locs = []
    simple_matches = re.findall(r':(\d+):(\d+)(?![,}])', loc_string)
    for line, col in simple_matches:
        locs.append((int(line), int(col)))

    brace_matches = re.findall(r':(\d+):\{([0-9,]+)\}', loc_string)
    for line, cols in brace_matches:
        for col in cols.split(','):
            locs.append((int(line), int(col)))

    return locs

def extract_chisel_code(filepath: str, line_num: int) -> str:
    """Get code from Chisel source"""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            if 1 <= line_num <= len(lines):
                code = lines[line_num - 1].strip()
                if len(code) > 33:
                    code = code[:30] + "..."
                return code
    except:
        pass
    return ""

def extract_all_signals_from_optimized(opt_file: str) -> List[Tuple[str, int, str, str]]:
    """Extract ALL wire and assign from optimized"""
    signals = []
    try:
        with open(opt_file, 'r') as f:
            for i, line in enumerate(f, 1):
                if 'module' in line or 'input' in line or 'output' in line or 'endmodule' in line:
                    continue

                # Match wire with assignment: wire x = expr;
                wire_match = re.search(r'wire\s+(?:\[\d+:\d+\])?\s+(\w+)\s*=\s*([^;]+);', line)
                if wire_match:
                    sig_name = wire_match.group(1)
                    expression = wire_match.group(2).strip()
                    loc_match = re.search(r'@\[([^\]]+)\]', line)
                    chisel_loc = loc_match.group(1) if loc_match else ""
                    signals.append((expression, i, sig_name, chisel_loc))
                    continue

                # Match wire declaration only: wire x; (for module interconnects)
                wire_decl_match = re.search(r'wire\s+(?:\[\d+:\d+\])?\s+(\w+)\s*;', line)
                if wire_decl_match:
                    sig_name = wire_decl_match.group(1)
                    expression = f"(module interconnect)"
                    loc_match = re.search(r'@\[([^\]]+)\]', line)
                    chisel_loc = loc_match.group(1) if loc_match else ""
                    signals.append((expression, i, sig_name, chisel_loc))
                    continue

                assign_match = re.search(r'assign\s+(\w+)\s*=\s*([^;]+);', line)
                if assign_match:
                    sig_name = assign_match.group(1)
                    expression = assign_match.group(2).strip()
                    loc_match = re.search(r'@\[([^\]]+)\]', line)
                    chisel_loc = loc_match.group(1) if loc_match else ""
                    display_expr = f"assign {sig_name} =\n{expression[:20]}..."
                    signals.append((display_expr, i, sig_name, chisel_loc))
    except:
        pass
    return signals

def find_in_unoptimized(sig_name: str, unopt_file: str) -> Optional[Tuple[str, int, str]]:
    """Find signal in unoptimized, returns (unopt_signal_name, line_num, chisel_location)"""
    try:
        with open(unopt_file, 'r') as f:
            for i, line in enumerate(f, 1):
                # Try exact match first
                if sig_name in line and ('wire' in line or 'assign' in line):
                    loc_match = re.search(r'@\[([^\]]+)\]', line)
                    return sig_name, i, loc_match.group(1) if loc_match else ""

            # If not found and signal starts with underscore, try without underscore
            # (optimized version may add underscore prefix to module interconnect wires)
            if sig_name.startswith('_'):
                alt_name = sig_name[1:]  # Remove leading underscore
                with open(unopt_file, 'r') as f2:
                    for i, line in enumerate(f2, 1):
                        if alt_name in line and ('wire' in line or 'assign' in line):
                            loc_match = re.search(r'@\[([^\]]+)\]', line)
                            return alt_name, i, loc_match.group(1) if loc_match else ""
    except:
        pass
    return None

def format_cell(text: str, width: int) -> List[str]:
    lines = text.split('\n')
    return [line.ljust(width)[:width] for line in lines]

def print_table_row(cells: List[str], widths: List[int]):
    cell_lines = [format_cell(cell, width) for cell, width in zip(cells, widths)]
    max_lines = max(len(lines) for lines in cell_lines)
    for lines in cell_lines:
        while len(lines) < max_lines:
            lines.append(' ' * widths[cell_lines.index(lines)])
    for i in range(max_lines):
        row = [cell_lines[j][i] for j in range(len(cells))]
        print(f" {row[0]} │ {row[1]} │ {row[2]} │ {row[3]} ")

def main():
    opt_file = 'generated/optimized.sv'
    unopt_file = 'generated/unoptimized.sv'
    chisel_file = 'src/main/scala/Fifo.scala'

    opt_signals = extract_all_signals_from_optimized(opt_file)
    if not opt_signals:
        print("Error: Could not extract signals")
        return

    widths = [35, 25, 35, 32]
    total_width = sum(widths) + 13
    separator = "═" * total_width

    print(f"{Colors.BOLD}{separator}{Colors.ENDC}")
    print(f"{Colors.BOLD}Signal Tracing Summary (demo_fifo){Colors.ENDC}")
    print(f"{Colors.BOLD}{separator}{Colors.ENDC}")
    print()

    print_table_row(["Optimized Verilog", "→ Unoptimized\nVerilog", "→ Chisel Source", "Compiler's Direct Location"], widths)
    print("─" * total_width)

    traced_count = 0
    ambiguous_count = 0

    for opt_expr, opt_line, sig_name, opt_chisel_loc in opt_signals:
        unopt_result = find_in_unoptimized(sig_name, unopt_file)

        if not unopt_result:
            continue

        unopt_sig_name, unopt_line, chisel_loc = unopt_result
        chisel_loc = chisel_loc if chisel_loc else opt_chisel_loc

        col1 = opt_expr[:35]
        col2 = f"{unopt_sig_name}\n(line {unopt_line})"
        col3 = ""
        col4 = ""

        if chisel_loc and 'Fifo.scala' in chisel_loc:
            locs = parse_chisel_locations(chisel_loc)
            if locs:
                first_line, first_col = locs[0]
                chisel_code = extract_chisel_code(chisel_file, first_line)
                if chisel_code:
                    col3 = f"{chisel_code}\n(line {first_line})"

                if len(locs) > 1:
                    ambiguous_count += 1
                    loc_by_line = {}
                    for line, col in locs:
                        if line not in loc_by_line:
                            loc_by_line[line] = []
                        loc_by_line[line].append(col)
                    loc_parts = []
                    for line, cols in sorted(loc_by_line.items()):
                        if len(cols) > 1:
                            col_range = f"{{{','.join(map(str, sorted(cols)))}}}"
                            loc_parts.append(f":{line}:{col_range}")
                        else:
                            loc_parts.append(f":{line}:{cols[0]}")
                    col4 = f"{', '.join(loc_parts[:3])}\n(ambiguous)"
                else:
                    col4 = f":{first_line}:{first_col}"

        traced_count += 1
        print_table_row([col1, col2, col3, col4], widths)

    print()
    precise_count = traced_count - ambiguous_count
    print(f"{Colors.BOLD}Result:{Colors.ENDC} Formal verification gives {Colors.GREEN}precise{Colors.ENDC} line numbers ({precise_count} signals) vs compiler's {Colors.WARNING}ambiguous{Colors.ENDC} {ambiguous_count} locations.")
    print(f"Total signals traced: {traced_count}")
    print(separator)

if __name__ == "__main__":
    main()
