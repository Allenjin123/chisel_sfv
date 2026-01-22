# Chisel-to-Verilog Signal Tracing via Formal Verification

## Problem Statement

When debugging optimized Verilog generated from Chisel, it's difficult to trace signals back to the original Chisel source code because:

1. **Optimization merges signals**: Multiple Chisel expressions become one Verilog expression
2. **Source locations are ambiguous**: Optimized Verilog comments list multiple Chisel lines without indicating which sub-expression came from which line

**Example** (from `generated/optimized.sv`):
```verilog
casez_tmp = _sum2_T + mul1 - mul3;  // @[scala:19:19, :21:19, :26:19, :27:19, :31:20, :34:38]
```
Which of the 6 listed Chisel lines does `_sum2_T + mul1` correspond to?

## Solution

Use **formal verification** to prove signal correspondence between optimized and unoptimized Verilog, then use unoptimized Verilog's clearer source locations to trace back to Chisel.

```
Optimized Verilog    ──equiv_add──>    Unoptimized Verilog    ────>    Chisel Source
(ambiguous locs)        (SAT proof)       (clear locs)              (line:column)
```

## Workflow

### Step 1: Generate FIRRTL from Chisel

```bash
sbt "runMain demo.GenerateFirrtl"
```

Output: `generated/ComplexExample.fir`

### Step 2: Generate Optimized Verilog

```bash
firtool generated/ComplexExample.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  -o generated/optimized.sv
```

Output: `generated/optimized.sv` - Signals merged, multiple source locations per line

### Step 3: Generate Unoptimized Verilog

```bash
firtool generated/ComplexExample.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  --disable-opt \
  --preserve-values=all \
  -o generated/unoptimized.sv
```

Output: `generated/unoptimized.sv` - All intermediate signals preserved with clear source locations

### Step 4: Trace Signal via Formal Verification

Given a target expression in optimized Verilog, use Yosys to prove which unoptimized signal it corresponds to:

```bash
yosys trace_expr2.ys
```

This proves that `_sum2_T + mul1 - mul3` (optimized) ≡ `expr2` (unoptimized).

## File Structure

```
demo_complex/
├── README.md                              # This file
├── build.sbt                              # Scala/Chisel build config
├── src/main/scala/
│   └── ComplexExample.scala               # Chisel source code
├── generated/
│   ├── ComplexExample.fir                 # FIRRTL intermediate
│   ├── optimized.sv                       # Optimized Verilog (signals merged)
│   └── unoptimized.sv                     # Unoptimized Verilog (signals preserved)
├── find_all_correspondences.py            # Automated correspondence finder
├── yosys_equiv.ys                         # Prove overall equivalence (optional)
└── trace_expr2.ys                         # Trace specific signal example
```

## Automated Signal Correspondence Finder

Instead of manually tracing signals, use the automated script:

```bash
python3 find_all_correspondences.py
```

This script:
1. Extracts all signals and their bit widths from both Verilog files
2. Tests only pairs with **matching bit widths** (reduces false positives)
3. Uses formal verification (`equiv_add` + `equiv_simple`) to prove equivalence
4. Verifies cells were actually added before claiming a match
5. Reports all correspondences with Chisel source locations

Example output:
```
Found 4 signal correspondences:

Gold (unoptimized)   Gate (optimized)     Width  Chisel Source
------------------------------------------------------------------------------------------
sum2                 _sum2_T              16     ComplexExample.scala:26:19
sum1                 _sum1_T              16     ComplexExample.scala:25:19
mul3                 mul3                 16     ComplexExample.scala:8:7, :19:19, :21:19
mul1                 mul1                 16     ComplexExample.scala:8:7, :19:19
```

## Example: Tracing `_sum2_T + mul1 - mul3`

### 1. Find the expression in optimized.sv

```bash
grep -n "_sum2_T + mul1" generated/optimized.sv
```

Output:
```
31:        casez_tmp = _sum2_T + mul1 - mul3;  // @[...scala:19:19, :21:19, :26:19, :27:19, :31:20, :34:38]
```

### 2. Identify candidate signals in unoptimized.sv

```bash
grep -E "sum1|sum2|diff|expr1|expr2" generated/unoptimized.sv
```

Candidates: `sum1`, `sum2`, `diff`, `expr1`, `expr2`

### 3. Use formal verification to find the match

Create `trace_expr2.ys`:
```tcl
read_verilog -sv generated/unoptimized.sv
rename ComplexExample gold
read_verilog -sv generated/optimized.sv
rename ComplexExample gate

proc
opt_clean
equiv_make gold gate equiv_mod
cd equiv_mod

# Test: is expr2 equivalent to the optimized expression?
equiv_add \expr2_gold $sub$generated/optimized.sv:31$24_Y_gate
equiv_simple
equiv_status
```

Run:
```bash
yosys trace_expr2.ys
```

Result:
```
Found 64 $equiv cells in equiv_mod:
  Of those cells 64 are proven and 0 are unproven.
  Equivalence successfully proven!
```

### 4. Look up source location in unoptimized.sv

```bash
grep -n "expr2" generated/unoptimized.sv
```

Output:
```
30:  wire [15:0] expr2 = _expr2_T[15:0];  // @[src/main/scala/ComplexExample.scala:31:20]
```

**Clear source location**: `ComplexExample.scala:31:20`

### 5. Go to Chisel source

```bash
sed -n '31p' src/main/scala/ComplexExample.scala
```

Output:
```scala
val expr2 = sum2 + diff     // Line 31: (a*c + b*d) + (a*b - a*c)
```

## Signal Correspondence Summary

| Chisel (Line) | Unoptimized Signal | Optimized Signal | Proved By |
|---------------|-------------------|------------------|-----------|
| `val mul1 = io.a * io.b` (19) | `mul1` | `mul1` | equiv_make (name match) |
| `val mul2 = io.c * io.d` (20) | `mul2` | *(inlined)* | - |
| `val mul3 = io.a * io.c` (21) | `mul3` | `mul3` | equiv_make (name match) |
| `val mul4 = io.b * io.d` (22) | `mul4` | *(inlined)* | - |
| `val sum1 = mul1 + mul2` (25) | `sum1` | `_sum1_T` | equiv_add |
| `val sum2 = mul3 + mul4` (26) | `sum2` | `_sum2_T` | equiv_add |
| `val diff = mul1 - mul3` (27) | `diff` | *(inlined)* | - |
| `val expr1 = sum1 * 2` (30) | `expr1` | *(inlined)* | - |
| `val expr2 = sum2 + diff` (31) | `expr2` | `_sum2_T + mul1 - mul3` | equiv_add |

## Key Yosys Commands

| Command | Purpose |
|---------|---------|
| `read_verilog -sv file.sv` | Load SystemVerilog file |
| `rename OldMod NewMod` | Rename module (to distinguish gold/gate) |
| `proc` | Convert processes to netlists |
| `equiv_make gold gate equiv_mod` | Create equivalence checking module |
| `equiv_add sig_gold sig_gate` | Add equivalence check for specific signals |
| `equiv_simple` | Prove equivalence using SAT |
| `equiv_induct` | Prove sequential equivalence using induction |
| `equiv_status` | Show proof results |

## Why This Approach?

| Aspect | Manual Tracing | Formal Verification |
|--------|---------------|---------------------|
| Correctness | Error-prone | Mathematically proven |
| Scalability | O(n²) signal comparisons | Automated |
| Complex expressions | Very difficult | Same difficulty |
| Sequential circuits | Nearly impossible | Use `equiv_induct` |

## Requirements

- Chisel 6.5.0
- firtool (CIRCT)
- Yosys 0.33+
- sbt
