# firtool Source Location Annotation Accuracy: Research Findings

> Research date: 2026-03-10
> Repos searched: [llvm/circt](https://github.com/llvm/circt), [chipsalliance/chisel](https://github.com/chipsalliance/chisel), [llvm/llvm-project](https://github.com/llvm/llvm-project)
> firtool version tested: 1.138.0

---

## Executive Summary

**The source location annotation problem in firtool-generated Verilog is real, acknowledged by CIRCT maintainers, and fundamentally unsolved.** Multiple issues have been filed since 2021, and the core problems remain open or were closed without fixes. The CIRCT project has invested heavily in a *separate* debug info system (HGLDD) rather than fixing the `@[...]` comment annotations, implicitly acknowledging that the comment-based approach has inherent architectural limitations.

This document catalogues every relevant finding, distinguishing between:
- Problems that are **unfixed and likely unfixable** in the current architecture
- Problems that were **partially patched** but root causes remain
- Problems that were **closed without fixes** (swept under the rug)
- **Alternative mechanisms** (HGLDD) and their current limitations

---

## 1. Unfixed Fundamental Problems

### 1.1 CSE Drops Source Locations (OPEN since Dec 2022)

**Issue**: [CIRCT #4358 — CSE Doesn't Merge Source Locators](https://github.com/llvm/circt/issues/4358)
**Status**: OPEN, no assigned fix, only 1 comment confirming the limitation
**Severity**: Fundamental — affects every design that has CSE-able operations

**Problem**: When MLIR's Common Subexpression Elimination deduplicates identical operations, the surviving operation retains only its *own* location. The eliminated operation's location is silently discarded.

**Reproduction** (from the issue):
```firrtl
circuit Foo:
  module Foo:
    input a: UInt<1>
    input b: UInt<1>
    node x = add(a, b)   ; line 6 — @[file:6:12]
    node y = add(a, b)   ; line 7 — @[file:7:12] ← THIS LOCATION IS LOST
```

After CSE, the `add` operation at line 7 is eliminated. Its location (`:7:12`) is NOT fused into the surviving operation — it simply vanishes. The output Verilog will have no trace that line 7 ever contributed to the computation.

**Root cause confirmed** by `dtzSiFive`:
> Looks like you're right, CSE will not fuse locations, but will keep the location of the replaced op if the original does not have a location ("unknown"):
> https://github.com/llvm/llvm-project/blob/22d87b82.../mlir/lib/Transforms/CSE.cpp#L200

**Why it's hard to fix**: This is an MLIR-level limitation. The upstream attempt to fix it was reverted (see Section 3).

---

### 1.2 Verilog Emitter Unions All Operand Locations (Architectural Limitation)

**No single issue tracks this**, but it is documented across multiple PRs and is inherent to the `ExportVerilog` design.

**Problem**: When the Verilog emitter renders an expression, it collects locations from ALL MLIR operations that contribute to the expression tree (operands, sub-operands, shared constants, type conversions). This causes locations from unrelated source lines to appear in a single Verilog annotation.

**Evidence from [CIRCT #2733](https://github.com/llvm/circt/issues/2733)** (real-world example, see Section 2.1):
```systemverilog
wire [3:0] _GEN_1 = {1'h0, value} + {1'h0, _incValue};
// /tmp/VendingMachine.fir:18:5, ImplicitStateVendingMachine.scala:13:26, :18:20, SimpleVendingMachine.scala:19:10
```
Only `ImplicitStateVendingMachine.scala:18:20` is correct. The others leaked from shared operands and type conversion ops.

**Why it's hard to fix**: The emitter's `LocationEmitter` class (in `ExportVerilog.cpp`) is designed to collect *all* contributing locations for an inlined expression. Changing this would require a fundamentally different emission strategy — either tracking which locations are "primary" vs "incidental", or never inlining expressions (which defeats the purpose of generating readable Verilog).

The `maximumNumberOfTermsPerExpression=1` workaround partially helps by breaking expressions into `_GEN` wires, but:
- Named signals (user `val`s) get cleaner locations
- `_GEN` wires themselves still have polluted locations
- The output Verilog becomes significantly less readable

---

### 1.3 Lowering-Phase Type Conversions Carry Source Locations

**No dedicated issue exists for this.** This is the primary mechanism you identified.

**Problem**: When FIRRTL operations are lowered to the HW/Comb dialect, implicit type conversions are created:
- Zero-extension (`{8'h0, signal}`) for width padding
- Truncation for width narrowing
- Concatenation for multi-width operations

These synthetic conversion operations inherit the location of the FIRRTL operation that triggered them. When two independent FIRRTL operations share an operand that needs the same padding, the padding operation is CSE'd, and one operation's location leaks into the other's expression tree.

**Example** (from your analysis):
```
val x = io.a * io.b  // line 15 — needs {8'h0, io.b}
val y = io.b * io.c  // line 16 — also needs {8'h0, io.b}
```
The shared zero-extension `{8'h0, io.b}` carries line 15's location. Signal `y`'s Verilog annotation incorrectly includes `:15:16`.

**Why it's hard to fix**: The conversion ops are a natural consequence of FIRRTL→HW lowering. They must carry *some* location for error reporting. But there's no mechanism to mark them as "synthetic/incidental" so the emitter could exclude them from location collection.

---

### 1.4 Constant Folding Erases Location Information Entirely

**Related upstream PR**: [llvm/llvm-project #75415 — Erase location of folded constants](https://github.com/llvm/llvm-project/pull/75415) (MERGED, Dec 2023)

**Problem**: MLIR's `OperationFolder` now sets the location of all CSE'd/folded constants to `UnknownLoc`. This means:

1. When `io.y * 0.U` folds to constant `0`, the constant has Unknown location — `io.y`'s contribution is completely lost.
2. When `term1 + 0` folds to `term1`, the addition is eliminated, and `term1`'s location no longer reflects that it was part of a more complex expression.
3. Any operation that relies on a CSE'd constant (`8'h0` for padding, etc.) will see `Unknown` locations for those operands.

**Current MLIR code** (`mlir/lib/Transforms/Utils/FoldUtils.cpp`):
```cpp
// erasedFoldedLocation is initialized as UnknownLoc::get(ctx)
existingOp->setLoc(erasedFoldedLocation);
```

**Why this is "by design"**: The MLIR team tried fusing locations (PR #74670, Dec 2023) but it caused OOM in production workloads at Google. Erasing to Unknown was the compromise — it's better than keeping a misleading first-user location, but worse than actually tracking all contributing locations.

---

### 1.5 Source Locator Path Issues (OPEN since May 2023)

**Issue**: [Chisel #3206 — Source Locators Are Absolute, but Missing Leading Slash](https://github.com/chipsalliance/chisel/issues/3206)
**Status**: OPEN

**Problem**: Chisel emits source locator paths like `Users/foo/bar/Foo.scala` — this looks relative but is actually an absolute path missing the leading `/`. This breaks:
- IDE integration (can't navigate to file)
- Error message display (no source context shown)
- Any tool trying to resolve file paths from annotations

---

### 1.6 Parser Errors Can't Point to Source Files (OPEN since Jul 2025)

**Issue**: [CIRCT #8725 — FIRParser: Errors during parsing only point at the .fir file](https://github.com/llvm/circt/issues/8725)
**Status**: OPEN

**Problem**: As FIRRTL moves more semantic checking into the parser (for "constructively correct" operations), error messages can only point to `.fir` file locations, not the original Scala/Chisel source. Users see:
```
<stdin>:9:5: error: expected passive value for force_initial source
```
instead of:
```
chisel-example.scala:17:15: error: ...
```

---

## 2. Real-World Bug Reports (Location Pollution in Practice)

### 2.1 Vending Machine Mux Location Contamination (CLOSED WITHOUT FIX)

**Issue**: [CIRCT #2733 — Incorrect location tracking in mux](https://github.com/llvm/circt/issues/2733)
**Status**: CLOSED (marked "completed") — **but NO fix was applied**
**Reporter**: `Kuree` (Keyi Zhang, hgdb author)
**Test case**: The real [ImplicitStateVendingMachine](https://github.com/chipsalliance/chisel3/blob/master/src/test/scala/examples/ImplicitStateVendingMachine.scala) from the Chisel3 test suite.

**Problem**: The generated Verilog for a simple register update shows locations from 3 different source files:
```systemverilog
wire [3:0] _GEN_1 = {1'h0, value} + {1'h0, _incValue};
// /tmp/VendingMachine.fir:18:5, ImplicitStateVendingMachine.scala:13:26, :18:20, SimpleVendingMachine.scala:19:10
```

Only `ImplicitStateVendingMachine.scala:18:20` is the correct source. The contamination sources:
- `/tmp/VendingMachine.fir:18:5` — `.fir` file location (partially addressed by `--strip-fir-debug-info`)
- `ImplicitStateVendingMachine.scala:13:26` — leaked from `doDispense` declaration that shared operands
- `SimpleVendingMachine.scala:19:10` — leaked from a completely unrelated assertion

**Resolution analysis**: The issue was closed by `youngar` on 2022-03-09 with only this comment:
> Thanks for reporting @Kuree!

**No linked commit, no PR, no fix.** The timeline shows a "connected" event but with no source issue number. This problem remains unfixed.

### 2.2 hgdb Debugging Prototype Hit Location Problems (OPEN, draft)

**Issue**: [CIRCT #2581 — Initial debugging support for circt](https://github.com/llvm/circt/pull/2581)
**Reporter**: `Kuree` (Keyi Zhang)

**Context**: This PR demonstrated source-level stepping through Chisel code in VSCode with Xcelium simulator. The author explicitly documented location problems:

> **Remaining issues:**
> 1. Incomplete/incorrect source location — register `cycle` is declared in `Counter.scala`, which is not in the working folder. In addition, all the filenames are also basenames, which makes it difficult to resolve during debugging, if there are conflicting names in the working directory.
> 2. Scoping information — it's unclear how to faithfully recreate the local variables given the current information in firrtl.

**Status**: Marked as draft by `darthscsi` in April 2023, who noted that `@fabianschuiki` was working on first-class debug information (the Debug dialect / HGLDD approach). This implicitly acknowledges that the existing location mechanism was insufficient for debugging.

---

## 3. MLIR Upstream CSE Location Saga (Attempted and Failed)

This timeline shows that the MLIR community tried to fix CSE location handling and **gave up due to scalability issues**:

| Date | PR | What Happened |
|------|-----|--------------|
| Dec 5, 2022 | [CIRCT #4358](https://github.com/llvm/circt/issues/4358) | Problem identified in CIRCT |
| Dec 7, 2023 | [llvm #74670](https://github.com/llvm/llvm-project/pull/74670) | **Merged**: Fuse locations of merged constants |
| Dec 12, 2023 | [llvm #75218](https://github.com/llvm/llvm-project/pull/75218) | **Merged**: Follow-up to flatten/deduplicate nested FusedLocs |
| Dec 13, 2023 | [llvm #75258](https://github.com/llvm/llvm-project/pull/75258) | **Closed**: Tried to fuse parent region location for hoisted constants |
| Dec 14, 2023 | [llvm #75381](https://github.com/llvm/llvm-project/pull/75381) | **REVERTED #74670 and #75218**: OOM/timeout in Google production (google-research/swirl-lm) |
| Dec 21, 2023 | [llvm #75415](https://github.com/llvm/llvm-project/pull/75415) | **Merged**: Compromise — erase locations of folded constants to `Unknown` |
| Aug 5, 2025 | [llvm #151573](https://github.com/llvm/llvm-project/pull/151573) | **Merged**: Don't erase location when moving within same block (TFLite needed names) |

**Key quote from the revert PR (#75381)**:
> We observed significant OOM/timeout issues due to #74670 to quite a few services including google-research/swirl-lm. The follow-up 75218 does not address the issue. Perhaps this is worth more investigation.

**Current state**: CSE'd constants have `Unknown` location. This is a **tradeoff between three bad options**:
1. Keep first user's location → location pollution (the original problem)
2. Fuse all locations → OOM on large designs
3. Erase to Unknown → location loss (current behavior)

None of these are acceptable for accurate source-level tracing.

---

## 4. Partial Fixes That Were Actually Applied

These issues were genuinely fixed, but they address *specific symptoms*, not the root cause:

### 4.1 FusedLoc Handling in Emitter
**[CIRCT #1563](https://github.com/llvm/circt/issues/1563)** (CLOSED, fixed by commit `10459d0e`, Aug 2021)
- Fixed: ExportVerilog now properly decomposes `FusedLoc` into individual locations.
- Limitation: Only fixed the *display* of fused locations, not the *creation* of incorrect fused locations.

### 4.2 Location Leaking Across If/Else Chains
**[CIRCT #4149](https://github.com/llvm/circt/pull/4149)** (MERGED, Oct 2022)
- Fixed: ExportVerilog no longer accumulates locations from all branches of an if/elseif chain.
- Limitation: Only fixes this specific emission pattern.

### 4.3 FusedLoc Nesting Bug
**[CIRCT #5349](https://github.com/llvm/circt/pull/5349)** (MERGED, Jun 2023)
- Fixed: FusedLoc creation was accidentally nesting instead of flattening, causing some locations to be repeated.

### 4.4 Parser Location Bug
**[CIRCT #1140](https://github.com/llvm/circt/issues/1140)** (CLOSED, fixed by commit `755f2af9`, May 2021)
- Fixed: FIR parser no longer assigns `.fir` file locations to sub-expressions when an `@[...]` locator is present.

### 4.5 Strip .fir Locations
**[CIRCT #3122](https://github.com/llvm/circt/pull/3122)** (MERGED, Jul 2022)
- Added `--strip-fir-debug-info` to remove `.fir` file locations before Verilog emission (enabled by default).
- Helps with one source of pollution but doesn't address Scala/Chisel location contamination.

### 4.6 Dedup Location Merging
**[CIRCT #2634](https://github.com/llvm/circt/pull/2634)** (MERGED, Feb 2022) and **[#4132](https://github.com/llvm/circt/pull/4132)** (MERGED, Oct 2022)
- Deduplication now fuses location info from deduplicated modules (instead of keeping only one).
- #4132 limited useless `.fir` locations in dedup — **15% performance gain, 50% memory reduction** on a large SiFive core.

---

## 5. HGLDD: The Alternative Approach (and Its Limitations)

CIRCT has invested significant effort into HGLDD (Hardware Generation Language Debug Database) as a **separate structured debug info format**, rather than fixing `@[...]` annotations. This implicitly acknowledges the annotations are a dead end for precise debugging.

### 5.1 HGLDD Architecture

HGLDD works by:
1. **Early capture** (`-g` flag): The `MaterializeDebugInfo` pass runs at the FIRRTL level, before lowering/CSE, creating `dbg.variable` ops for every port, wire, node, and register.
2. **Pipeline survival**: Debug ops are maintained through the pipeline as the IR is transformed.
3. **Verilog location annotation** (`emitVerilogLocations`): After Verilog emission, output locations are annotated back onto MLIR ops.
4. **JSON emission** (`--emit-hgldd`): A separate `*.dd` file maps source locations → Verilog signals.

### 5.2 HGLDD Merged PRs

| PR | Date | What it adds |
|----|------|-------------|
| [#6308](https://github.com/llvm/circt/pull/6308) | Oct 2023 | Debug dialect (`dbg.variable`, `dbg.struct`, `dbg.array`) |
| [#6309](https://github.com/llvm/circt/pull/6309) | Oct 2023 | `-g` flag and `MaterializeDebugInfo` pass |
| [#6148](https://github.com/llvm/circt/pull/6148) | Oct 2023 | `--emit-hgldd` and `--emit-split-hgldd` |
| [#6334](https://github.com/llvm/circt/pull/6334) | Nov 2023 | Expression reconstruction in HGLDD |
| [#6335](https://github.com/llvm/circt/pull/6335) | Oct 2023 | Debug-only value/op analysis |
| [#6451](https://github.com/llvm/circt/pull/6451) | Dec 2023 | Relative file paths in HGLDD |
| [#6452](https://github.com/llvm/circt/pull/6452) | Nov 2023 | Only mention existing files |
| [#6453](https://github.com/llvm/circt/pull/6453) | Nov 2023 | Skip debug ops in ExportVerilog |
| [#6454](https://github.com/llvm/circt/pull/6454) | Dec 2023 | `dbg.scope` operation |
| [#6511](https://github.com/llvm/circt/pull/6511) | Dec 2023 | Inline scope support |
| [#6512](https://github.com/llvm/circt/pull/6512) | Jan 2024 | Scopes for inlined modules |
| [#6750](https://github.com/llvm/circt/pull/6750) | Feb 2024 | Fix instance output port emission |
| [#6753](https://github.com/llvm/circt/pull/6753) | Feb 2024 | Uniquify object names |

### 5.3 HGLDD Known Limitations (OPEN Issues)

| Issue | Problem |
|-------|---------|
| [#6816](https://github.com/llvm/circt/issues/6816) | OPEN: Cannot emit HW struct and array types (only `dbg.struct`/`dbg.array` ops, not native HW types) |
| [#6983](https://github.com/llvm/circt/issues/6983) | OPEN: No Chisel type information in HGLDD (only FIRRTL types) |
| [#7246](https://github.com/llvm/circt/pull/7246) | OPEN PR: Tywaves adding Chisel type annotations (not yet merged) |

### 5.4 HGLDD Is Not a Format Designed for Formal Verification

HGLDD was designed for **waveform debugging** (Synopsys Verdi, Surfer) — mapping Verilog signals back to source for interactive exploration. It is:
- **Signal-oriented**: Maps variables (ports, wires, regs) to source locations
- **Expression-aware**: Can represent how source-level values are reconstructed from Verilog signals
- **NOT assertion-oriented**: No mechanism to map verification conditions or assertions back to source

For formal verification use cases (mapping SVA properties, assert conditions, or counterexample signals back to Chisel source), HGLDD provides partial coverage — you can trace individual signals, but not the higher-level semantic structure of assertions.

---

## 6. All firtool Flags Related to Location/Debug

### 6.1 Flags You've Tried

| Flag | Effect on your problem |
|------|----------------------|
| `--disable-opt --preserve-values=all` | Doesn't prevent CSE during lowering |
| `--prefer-info-locators` | Controls which locator to prefer (info vs .fir), not relevant to pollution |
| `--lowering-options=maximumNumberOfTermsPerExpression=1` | Partially helps — breaks expressions into `_GEN` wires, but `_GEN` locations still polluted |
| `--mlir-print-debuginfo` | Confirmed that MLIR ops have clean locations; pollution happens in emitter |

### 6.2 Flags You May Not Have Tried

| Flag | What it does | Relevance |
|------|-------------|-----------|
| **`-g`** | Enables `MaterializeDebugInfo` — captures debug info early | High: structured alternative to `@[...]` |
| **`--emit-hgldd`** | Emits HGLDD JSON debug info alongside Verilog | High: separate debug info channel |
| `--lowering-options=emitVerilogLocations` | Records Verilog output positions on MLIR ops | Medium: needed for HGLDD |
| `--lowering-options=wireSpillingHeuristic=spillLargeTermsWithNamehints` | Spills named expressions to wires | Medium: similar to `maximumNumberOfTermsPerExpression` but smarter |
| `--lowering-options=disallowMuxInlining` | Spills every mux to a wire | Medium: reduces expression tree depth |
| `--lowering-options=locationInfoStyle=none` | Suppresses `@[...]` comments entirely | Low: useful if relying on HGLDD instead |
| `--strip-fir-debug-info` | Remove `.fir` file locations (enabled by default) | Low: already on |

### 6.3 Undocumented / Less-Known Options

| Flag | Source |
|------|--------|
| `--lowering-options=wireSpillingNamehintTermLimit=N` | Controls threshold for spilling named terms (default=3) |
| `--lowering-options=printDebugInfo` | Emit additional debug info (inner symbols) into comments |
| `--ignore-info-locators` | Use `.fir` locations instead of `@[...]` locators |

---

## 7. Key People and Their Roles

| Person | Affiliation | Role in this area |
|--------|------------|-------------------|
| `@fabianschuiki` | CIRCT maintainer | Led Debug dialect / HGLDD design and implementation |
| `@dtzSiFive` | SiFive | Identified CSE location issue, major ExportVerilog contributor |
| `@lattner` | CIRCT founder | Fixed early location bugs (#1140, #1563) |
| `@seldridge` | SiFive | FIRRTL dialect maintainer, filed #8725, #3206 |
| `@youngar` | CIRCT contributor | Port locations (#4540), closed #2733 without fix |
| `@Kuree` | (Keyi Zhang) | hgdb author, reported #2733, demonstrated source-level debugging |
| `@rameloni` | (Raffaele Meloni) | Tywaves project, working on Chisel→HGLDD pipeline |
| `@uenoku` | CIRCT contributor | locationInfoStyle, strip-fir-debug-info |

---

## 8. Assessment: Does the Current Workflow Have Unfixed Problems?

**Yes, unequivocally.** The following problems are confirmed unfixed:

### 8.1 Problems That Are Unfixed AND Hard to Fix

1. **CSE location loss** (#4358, OPEN since 2022): When identical operations are CSE'd, one location is silently lost. The MLIR upstream attempted a fix and reverted it due to OOM. The current "solution" — erasing to Unknown — makes the problem different but not better.

2. **Verilog emitter location union**: The emitter collects locations from ALL operands in an inlined expression tree. This is architecturally fundamental to how ExportVerilog works and has no proposed fix.

3. **Lowering-introduced type conversion contamination**: Zero-extension, truncation, and concatenation ops created during FIRRTL→HW lowering carry their parent FIRRTL op's location, causing cross-contamination when shared. No issue tracks this, no fix proposed.

4. **Constant folding location erasure**: MLIR's OperationFolder erases folded constant locations to Unknown (by design, since the "fuse" approach OOM'd). Any computation that simplifies through constant folding loses its source trace.

### 8.2 Problems That Are Unfixed AND Affect Real Projects

- **#2733**: Real VendingMachine example from Chisel3 test suite showed polluted locations. Closed without fix.
- **#2581**: hgdb debugging prototype hit "incomplete/incorrect source location" on real Chisel examples. Marked as draft, superseded by HGLDD (which doesn't solve the same problem).
- **Chisel #3206**: Source file paths are broken (missing leading `/`). Still open.
- **#8725**: Error messages can't point to Chisel source files. Still open.

### 8.3 HGLDD Does Not Fully Solve This

HGLDD is the best available alternative, but:
- It maps **individual signals** to source, not **expressions** or **assertions** to source
- It requires `-g --emit-hgldd` which many users don't use
- It has no mechanism for formal verification-specific tracing
- Struct/array support is incomplete (#6816)
- Chisel type information is not yet available (#7246, PR not merged)
- It produces a separate JSON file that requires tooling to consume

### 8.4 What This Means for Your Framework

The `@[file:line:col]` annotations in firtool-generated Verilog are **fundamentally unreliable** for precise source-level tracing due to architectural issues that the CIRCT project has acknowledged but chosen not to (or been unable to) fix. The existing HGLDD system provides an alternative channel but was designed for waveform debugging, not formal verification.

**Your framework fills a genuine gap**: accurate, per-signal source location mapping that survives the compilation pipeline — something that neither the `@[...]` annotations nor HGLDD currently provide with sufficient fidelity for formal verification use cases.

---

## 9. Summary Table: All Issues by Status

### OPEN / Unfixed

| Issue | Title | Filed | Problem |
|-------|-------|-------|---------|
| [CIRCT #4358](https://github.com/llvm/circt/issues/4358) | CSE Doesn't Merge Source Locators | Dec 2022 | CSE drops second op's location |
| [CIRCT #899](https://github.com/llvm/circt/issues/899) | Improve location options | Apr 2021 | No `\`line` directive support |
| [CIRCT #6816](https://github.com/llvm/circt/issues/6816) | HGLDD: Emit HW struct/array types | Jun 2024 | HGLDD can't handle native HW types |
| [CIRCT #6983](https://github.com/llvm/circt/issues/6983) | Chisel type annotation for Tywaves | May 2024 | No Chisel type info in debug output |
| [CIRCT #8725](https://github.com/llvm/circt/issues/8725) | Parser errors only point at .fir file | Jul 2025 | Can't trace parser errors to Chisel |
| [CIRCT #6417](https://github.com/llvm/circt/issues/6417) | Unknown location attrs on HWModule ports | Nov 2023 | Unknown vs missing location inconsistency |
| [CIRCT #9817](https://github.com/llvm/circt/issues/9817) | Option to disable RAUW in LowerLayers | Mar 2026 | RAUW degrades signal readability |
| [Chisel #3206](https://github.com/chipsalliance/chisel/issues/3206) | Source locators missing leading slash | May 2023 | Broken file paths |
| [Chisel #4015](https://github.com/chipsalliance/chisel/issues/4015) | Pass Chisel info to firtool (Tywaves) | Apr 2024 | No Chisel-level debug info in firtool |
| [CIRCT #7246](https://github.com/llvm/circt/pull/7246) | Tywaves annotations in HGLDD (PR) | Oct 2024 | Not yet merged |

### Closed Without Fix

| Issue | Title | Filed | How it was closed |
|-------|-------|-------|-------------------|
| [CIRCT #2733](https://github.com/llvm/circt/issues/2733) | Incorrect location tracking in mux | Mar 2022 | Closed with "Thanks for reporting!" — no commit, no PR |

### Closed With Partial/Specific Fixes

| Issue | Title | What was fixed | What remains |
|-------|-------|---------------|-------------|
| [CIRCT #1563](https://github.com/llvm/circt/issues/1563) | Not handling fused locations well | Emitter now decomposes FusedLoc | Root cause of bad FusedLocs unfixed |
| [CIRCT #4149](https://github.com/llvm/circt/pull/4149) | Don't combine locs across if/elseif | Fixed this specific pattern | General expression union unfixed |
| [CIRCT #5349](https://github.com/llvm/circt/pull/5349) | Fix fusing locations append/nesting | Fixed FusedLoc chaining bug | Doesn't prevent bad fusions |
| [CIRCT #1140](https://github.com/llvm/circt/issues/1140) | Parser locations set wrong | Parser fixed | Lowering-phase locations unfixed |
| [llvm #75415](https://github.com/llvm/llvm-project/pull/75415) | Erase location of folded constants | No more misleading first-user loc | Location info now lost entirely |

### MLIR Upstream (Attempted Fix, Reverted)

| PR | Title | Status |
|----|-------|--------|
| [llvm #74670](https://github.com/llvm/llvm-project/pull/74670) | Fuse locations of merged constants | Merged then **reverted** (OOM) |
| [llvm #75218](https://github.com/llvm/llvm-project/pull/75218) | Flatten fused locations | Merged then **reverted** (OOM) |
| [llvm #75381](https://github.com/llvm/llvm-project/pull/75381) | Revert of above | Applied |
| [llvm #75415](https://github.com/llvm/llvm-project/pull/75415) | Erase to Unknown (compromise) | **Merged** (current behavior) |
