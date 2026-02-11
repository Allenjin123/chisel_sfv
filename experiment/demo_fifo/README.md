# FIFO Example - Double Buffer FIFO with Sequential Logic

This example demonstrates a FIFO (First-In-First-Out queue) implementation with a state machine, using Yosys for sequential circuit equivalence checking.

## File Description

### Chisel Source Code
- **src/main/scala/Fifo.scala** - Chisel hardware description implementing a double buffer FIFO
  - `DoubleBuffer`: Single double buffer stage with three states (empty, one, two)
  - `DoubleBufferFifo`: Multi-stage FIFO
  - `DoubleBufferFifoTop`: Top-level module (depth=4, i.e., 2 double buffer stages)

### Generated Files
- **generated/DoubleBufferFifo.fir** - FIRRTL intermediate representation
- **generated/unoptimized.sv** - Unoptimized SystemVerilog (preserves all intermediate signals and source annotations)
- **generated/optimized.sv** - Optimized SystemVerilog (may merge logic)

### Yosys Equivalence Checking Scripts
- **yosys/test_outputs.ys** - Bounded verification: I/O output ports only
- **yosys/test_registers.ys** - Bounded verification: registers + output ports
- **yosys/test_wires.ys** - Bounded verification: individual intermediate signal correspondence
- **yosys/test_induct.ys** - Unbounded verification: k-induction (temporal induction)


## Usage Steps

### 1. Generate FIRRTL
```bash
sbt "runMain fifo.GenerateFirrtl"
```

### 2. Generate Unoptimized Verilog
```bash
firtool generated/DoubleBufferFifo.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  --disable-opt \
  --preserve-values=all \
  -o generated/unoptimized.sv
```

### 3. Generate Optimized Verilog
```bash
firtool generated/DoubleBufferFifo.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  -o generated/optimized.sv
```

### 4. Run Equivalence Checking
```bash
cd yosys
yosys -s test_induct.ys       # Unbounded: k-induction
```


## Equivalence Checking Methods

### Overall Flow (reference: [fsyn](https://github.com/YosysHQ/yosys/tree/main/passes/opt/fsyn))

1. **Load gold**: `read_verilog -formal` → `prep -flatten` → `rename -top gold` → `clk2fflogic`
2. **Stash gold**: `design -stash gold`
3. **Load gate**: Same as above, `rename -top gate`
4. **Merge**: `design -copy-from gold -as gold gold`
5. **Create miter**: `miter -equiv -flatten -make_outputs gold gate miter`
6. **Prove**: `sat -prove trigger 0 ...`

Key command explanations:
- **`clk2fflogic`** — Converts clock-driven DFFs to `$ff` cells, enabling the SAT solver to correctly handle sequential logic
- **`design -stash/copy-from`** — Manages two independent designs within the same Yosys session
- **`expose -dff -shared`** — Promotes registers with the same name in both modules to output ports (`-dff` matches only registers, avoiding mismatches with combinational signals that share names but have different logic)
- **`miter -equiv -flatten -make_outputs`** — Automatically creates a miter circuit; `trigger` signal equals 1 when outputs differ
- **`-set-init-zero`** — Initializes all registers to 0 (reset state)

### Bounded vs Unbounded Verification

| Method | Command | Scope | Use Case |
|--------|---------|-------|----------|
| Bounded BMC | `sat -prove trigger 0 -set-init-zero -seq N` | N cycles from reset | Quick checks, small modules |
| Unbounded k-induction | `sat -tempinduct -prove trigger 0 -set-init-zero -seq 2` | All reachable states | Complete proof |

### Key Points of k-Induction

`-tempinduct` performs k-induction:
- **Base case**: Starting from the initial state (`-set-init-zero`), the property holds for k steps
- **Inductive step**: Starting from **any state** where the property has held for k steps, prove it still holds at step k+1

**Important**: Proving equivalence of a single intermediate signal (e.g., `stateReg == 2'h2`) alone will cause the inductive step to hang because the induction hypothesis is too weak — knowing "comparison results are equal for k steps" cannot imply "register values are equal".

Solution: Prove the target signal together with register equivalence (`-prove trigger 0 -prove wireA wireB`), using register equivalence to **strengthen the induction hypothesis**. Same state + same input = same next state — this is an inductive invariant.

### Intermediate Signal Tracing

By proving that signals in optimized.sv are equivalent to signals in unoptimized.sv, and leveraging source annotations in unoptimized.sv (`// @[Fifo.scala:46:20]`), optimized signals can be traced back to Chisel source code.

For example, `stateReg == 2'h2` in optimized.sv (Yosys internal name `$eq$...:21$103_Y`) corresponds to `_io_deq_valid_T_1` in unoptimized.sv, with annotation pointing to `Fifo.scala:59` (`io.deq.valid := stateReg === one || stateReg === two`).
