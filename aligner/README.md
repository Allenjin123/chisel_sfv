# Aligner — Trace Optimized Verilog Signals Back to Chisel Source

Given a signal or sub-expression in optimized Verilog, formally proves which signals in the unoptimized Verilog are equivalent, then reports their Chisel source annotations.

## How It Works

1. Creates a Yosys miter circuit with gold (unoptimized) and gate (optimized) side-by-side
2. Finds the gate signal matching the user's `--loc` via the Yosys `\src` attribute
3. Proves equivalence against all gold signals of matching width using `sat -tempinduct` (k-induction)
4. Reports equivalent gold signals with their `@[Fifo.scala:line:col]` annotations

## Usage

```bash
python3 trace_signal.py --gate <optimized.sv> --gold <unoptimized.sv> --loc <line.startcol-endcol>
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--gate`, `-G` | Path to optimized SystemVerilog |
| `--gold`, `-g` | Path to unoptimized SystemVerilog (with Chisel source annotations) |
| `--loc`, `-l` | Signal location in gate file: `<line>.<startcol>-<endcol>` |
| `--module`, `-m` | Module name (auto-detected if omitted) |
| `--bounded`, `-b` | Use bounded BMC instead of unbounded k-induction |

### Finding the `--loc` value

Open the optimized Verilog and identify the expression you want to trace. The `--loc` format is `line.startcol-endcol` (1-indexed), matching the Yosys `\src` attribute format.

For example, in `optimized.sv` line 21:
```
  wire       _GEN_2 = stateReg == 2'h2 & io_deq_ready;
                       ^col 23          ^col 39
```

- `21.23-39` targets the sub-expression `stateReg == 2'h2`
- `21.14-20` targets the named wire `_GEN_2`

If unsure, pass an invalid location -- the error output lists all available signals with their `src` ranges:
```bash
python3 trace_signal.py --gate optimized.sv --gold unoptimized.sv --loc 0.0-0
```

## Examples

```bash
# Trace "stateReg == 2'h2" (sub-expression on line 21, cols 23-39)
python3 trace_signal.py \
  --gate ../experiment/demo_fifo/generated/optimized.sv \
  --gold ../experiment/demo_fifo/generated/unoptimized.sv \
  --loc 21.23-39

# Output:
#   _GEN_6              -> Fifo.scala:46:20   (is(two) case match)
#   _io_deq_valid_T_1   -> Fifo.scala:59:51   (io.deq.valid expression)

# Trace named wire "_GEN_0" (line 19, cols 14-20)
python3 trace_signal.py \
  --gate ../experiment/demo_fifo/generated/optimized.sv \
  --gold ../experiment/demo_fifo/generated/unoptimized.sv \
  --loc 19.14-20

# Output:
#   _GEN_4              -> Fifo.scala:41:28   (io_deq_ready & io_enq_valid)

# Use bounded BMC (faster, but not a complete proof)
python3 trace_signal.py \
  --gate ../experiment/demo_fifo/generated/optimized.sv \
  --gold ../experiment/demo_fifo/generated/unoptimized.sv \
  --loc 21.23-39 --bounded


# Comb only
python3 trace_signal.py --gate ../experiment/demo_verilog/generated/optimized.sv --gold ../experiment/demo_verilog/generated/unoptimized.sv --loc 14.9-40
```

## Prerequisites

- [Yosys](https://github.com/YosysHQ/yosys) (with `sat` command support)
- Python 3.6+

## Bounded vs Unbounded

| Mode | Flag | Method | Completeness |
|------|------|--------|-------------|
| Unbounded (default) | -- | `sat -tempinduct` (k-induction) | Complete proof for all reachable states |
| Bounded | `--bounded` | `sat -prove -seq 2` | Proof for 2 cycles from reset only |

The unbounded mode strengthens the induction hypothesis by proving register equivalence (`-prove trigger 0`) alongside each wire pair, ensuring the proof converges.
