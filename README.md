# Chisel-to-Verilog Signal Tracing via Formal Verification

## Problem Statement

When debugging optimized Verilog generated from Chisel, it's difficult to trace signals back to the original Chisel source code because:

1. **Optimization merges signals**: Multiple Chisel expressions become one Verilog expression
2. **Source locations are ambiguous**: Optimized Verilog comments list multiple Chisel lines without indicating which sub-expression came from which line

**Example** (from `optimized.sv`):
```verilog
wire _GEN_2 = stateReg == 2'h2 & io_deq_ready;  // @[Fifo.scala:26:27, :27:22, :30:22, :46:20, :51:29, :52:19]
```
Which of the 6 listed Chisel lines does `stateReg == 2'h2` correspond to?

## Solution

Use **formal verification** to prove signal correspondence between optimized and unoptimized Verilog, then use the unoptimized version's precise source annotations to trace back to Chisel.

```
Optimized Verilog  ──SAT prove──>  Unoptimized Verilog  ────>  Chisel Source
(ambiguous locs)    (k-induction)   (clear locs)               (line:column)
```

## Project Structure

```
chisel_sfv/
├── aligner/                        # Signal tracing tool
│   ├── trace_signal.py             # Main script
│   └── README.md
├── experiment/
│   ├── demo_fifo/                  # Sequential circuit example (DoubleBuffer FIFO)
│   │   ├── src/main/scala/         # Chisel source
│   │   ├── generated/              # optimized.sv + unoptimized.sv
│   │   ├── yosys/                  # Yosys equivalence checking scripts
│   │   └── README.md
│   └── demo_verilog/               # Combinational circuit example (Figure5Example)
│       ├── src/main/scala/
│       └── generated/
└── README.md                       # This file
```

## Quick Start

### 1. Generate Verilog from Chisel

```bash
cd experiment/demo_fifo
sbt "runMain fifo.GenerateFirrtl"

# Unoptimized (preserves all intermediate signals + source annotations)
firtool generated/DoubleBufferFifo.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  --disable-opt --preserve-values=all \
  -o generated/unoptimized.sv

# Optimized
firtool generated/DoubleBufferFifo.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  -o generated/optimized.sv
```

### 2. Trace a Signal

```bash
cd aligner

# Find what "stateReg == 2'h2" in optimized.sv corresponds to in Chisel
python3 trace_signal.py \
  --gate ../experiment/demo_fifo/generated/optimized.sv \
  --gold ../experiment/demo_fifo/generated/unoptimized.sv \
  --loc 21.23-39
```

Output:
```
  Signal                    Width  Chisel Source
  ───────────────────────── ───── ────────────────────────────────────────
  _GEN_6                    1      Fifo.scala:46:20
  _io_deq_valid_T_1         1      Fifo.scala:59:51
```

The `--loc` argument specifies the target expression's position in optimized.sv as `line.startcol-endcol`. To discover available signals, pass an invalid location (e.g., `--loc 0.0-0`) and the script lists all signals with their `src` ranges.

See [aligner/README.md](aligner/README.md) for full usage details.

## How It Works

### Miter Circuit Approach (via [fsyn](https://github.com/YosysHQ/yosys/tree/main/passes/opt/fsyn))

1. Load both designs into Yosys, flatten, and convert clocks (`clk2fflogic`)
2. Create a miter circuit that shares inputs but keeps internal state independent
3. Use `sat -tempinduct` (k-induction) to prove signal equivalence for all reachable states

```
read_verilog -formal unoptimized.sv
prep -flatten -top Module
rename -top gold
clk2fflogic
design -stash gold

read_verilog -formal optimized.sv
prep -flatten -top Module
rename -top gate
clk2fflogic

design -copy-from gold -as gold gold
miter -equiv -flatten -make_outputs gold gate miter
hierarchy -top miter

sat -tempinduct -prove trigger 0 -prove \gold.sigA \gate.sigB -set-init-zero -seq 2 miter
```

### Key Insight: Strengthened Induction

Proving a single intermediate signal (e.g., `stateReg == 2'h2`) in isolation causes k-induction to hang -- the hypothesis "comparison results matched for k steps" is too weak to imply "register values are equal."

The fix: prove the target signal **alongside register equivalence** (`-prove trigger 0`). Same state + same inputs = same next state, which is an inductive invariant.

### Supported Circuits

| Type | Method | Example |
|------|--------|---------|
| Combinational | `sat -tempinduct` (converges at k=1) | demo_verilog (Figure5Example) |
| Sequential | `sat -tempinduct` with trigger strengthening | demo_fifo (DoubleBuffer) |

## Requirements

- [Yosys](https://github.com/YosysHQ/yosys) 0.33+
- Python 3.6+
- [firtool](https://github.com/llvm/circt) (CIRCT) for generating Verilog from Chisel
- sbt + Chisel 6.5.0 for the example projects
