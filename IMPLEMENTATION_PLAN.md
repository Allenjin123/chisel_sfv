# K-Step Induction Implementation Plan for CIRCT

## Overview

This document outlines the plan to implement k-step induction for sequential
equivalence checking in CIRCT IR, based on the algorithms from:
- "Scalable and Scalably-Verifiable Sequential Synthesis" (Mishchenko et al.)
- ABC's `ssw` (signal-sweeping) implementation

## Phase 1: Foundation (Weeks 1-3)

### 1.1 Understand CIRCT Infrastructure
- [ ] Study `circt-bmc` implementation in detail
- [ ] Study `verif` dialect operations (`verif.bmc`, `verif.assert`, `verif.assume`)
- [ ] Study `seq` dialect for register handling (`seq.compreg`, `seq.firreg`)
- [ ] Study SMT dialect and lowering passes
- [ ] Run existing examples through the pipeline

**Key files to study:**
```
circt/lib/Dialect/Verif/
circt/lib/Dialect/Seq/
circt/lib/Dialect/SMT/
circt/tools/circt-bmc/
```

### 1.2 Extend Python Prototype
- [ ] Add `seq.compreg` support to `prove_correspondence.py`
- [ ] Implement simple 1-step induction in Python first
- [ ] Test on simple sequential examples

```python
# Example extension for seq.compreg
elif op_type == 'seq.compreg':
    # %reg = seq.compreg %input, %clk : i8
    # In frame f: reg_f = input_{f-1}
    # In frame 0: reg_0 = initial_value (or free variable)
    pass
```

### 1.3 Create Sequential Test Cases
- [ ] Simple counter (1 register)
- [ ] Two equivalent counters (different implementations)
- [ ] Shift register
- [ ] FSM examples

```
// Example: Two equivalent shift registers
hw.module @shift1(in %clk: !seq.clock, in %in: i8, out out: i8) {
  %r1 = seq.compreg %in, %clk : i8
  %r2 = seq.compreg %r1, %clk : i8
  hw.output %r2 : i8
}

hw.module @shift2(in %clk: !seq.clock, in %in: i8, out out: i8) {
  // Different structure, same behavior
  ...
}
```

## Phase 2: Core Algorithm (Weeks 4-8)

### 2.1 Design MLIR Operations

Create new operations for k-step induction (extend `verif` dialect or create new dialect):

```mlir
// Option A: Extend verif dialect
verif.k_induction bound %k {
  // Circuit with registers
  ^bb0(%inputs..., %state...):
    // combinational logic
    verif.yield %outputs..., %next_state...
} init {
  // Initial state specification
  ^bb0:
    verif.yield %init_state...
} equivalences {
  // Candidate equivalence pairs
  verif.equiv %a, %b
  verif.equiv %c, %d
}

// Option B: Decompose into existing operations
verif.bmc_base bound %k init %init_state { ... }  // Base case
verif.inductive_step frames %k { ... }             // Inductive case
```

### 2.2 Implement Frame Unrolling

Create a pass that unrolls k frames with speculative reduction:

```cpp
// Pseudo-code for frame unrolling
class FrameUnroller {
  // Unroll k frames of combinational logic
  // For inductive case: registers become free variables in frame 0
  // For base case: registers start at initial state

  void unrollFrame(int frameIdx, bool speculativeReduction) {
    // Map register outputs to frame inputs
    for (auto reg : registers) {
      if (frameIdx == 0) {
        // Frame 0: free variable (inductive) or init value (base)
        setFrameValue(reg, frameIdx, createFreeVar());
      } else {
        // Frame f: connected to frame f-1 register input
        setFrameValue(reg, frameIdx, getFrameValue(reg.input, frameIdx-1));
      }
    }

    // Process combinational logic
    for (auto op : combOps) {
      auto result = processOp(op, frameIdx);

      // Speculative reduction: merge equivalent nodes
      if (speculativeReduction && hasEquivRepr(op)) {
        auto repr = getEquivRepr(op);
        setFrameValue(op, frameIdx, getFrameValue(repr, frameIdx));
        addConstraint(result == getFrameValue(repr, frameIdx));
      } else {
        setFrameValue(op, frameIdx, result);
      }
    }
  }
};
```

### 2.3 Implement Equivalence Class Management

```cpp
// Data structure for equivalence classes
class EquivalenceClasses {
  // Map from node to representative
  DenseMap<Value, Value> nodeToRepr;

  // Map from representative to class members
  DenseMap<Value, SmallVector<Value>> reprToClass;

  // Initialize from simulation
  void initFromSimulation(ArrayRef<SimulationPattern> patterns);

  // Refine using counterexample
  void refine(ArrayRef<Value> counterexample);

  // Get representative for a node
  Value getRepr(Value node);

  // Check if two nodes are in same class
  bool areEquivalent(Value a, Value b);
};
```

### 2.4 Implement Base Case (BMC)

Reuse concepts from `circt-bmc` but adapted for equivalence checking:

```cpp
// Base case: prove equivalences from initial state for k frames
LogicalResult runBaseCase(
    ModuleOp circuit,
    EquivalenceClasses &classes,
    int k,
    Value initialState) {

  for (int f = 0; f < k; f++) {
    // Unroll frame f from initial state
    auto frame = unrollFrame(circuit, f, /*speculativeReduction=*/false);

    // For each candidate equivalence
    for (auto &[node, repr] : classes) {
      if (node == repr) continue;

      auto nodeVal = getFrameValue(node, f);
      auto reprVal = getFrameValue(repr, f);

      // SAT query: can they differ?
      if (satCheck(nodeVal != reprVal) == SAT) {
        // Disproved: refine classes
        classes.refine(getCounterexample());
      }
      // If UNSAT: equivalence holds for this frame (merge for efficiency)
    }
  }
  return success();
}
```

### 2.5 Implement Inductive Case with Speculative Reduction

```cpp
// Inductive case: assume equivalences in frames 0..k-1, prove in frame k
LogicalResult runInductiveCase(
    ModuleOp circuit,
    EquivalenceClasses &classes,
    int k) {

  // Build k frames with speculative reduction
  auto frames = unrollFramesWithSpeculativeReduction(circuit, k, classes);

  // Add constraints for speculated equivalences in frames 0..k-1
  for (int f = 0; f < k; f++) {
    for (auto &[node, repr] : classes) {
      if (node == repr) continue;
      addConstraint(getFrameValue(node, f) == getFrameValue(repr, f));
    }
  }

  // Prove equivalences in frame k
  for (auto &[node, repr] : classes) {
    if (node == repr) continue;

    auto nodeVal = getFrameValue(node, k);
    auto reprVal = getFrameValue(repr, k);

    // SAT query: can they differ (given constraints)?
    if (satCheck(nodeVal != reprVal) == SAT) {
      // Disproved: refine classes and restart
      classes.refine(getCounterexample());
      return failure(); // Need another iteration
    }
  }

  return success(); // All equivalences proved inductively
}
```

## Phase 3: Integration (Weeks 9-11)

### 3.1 Create CIRCT Pass

```cpp
// lib/Dialect/Verif/Transforms/KStepInduction.cpp
class KStepInductionPass : public impl::KStepInductionBase<KStepInductionPass> {
public:
  void runOnOperation() override {
    auto module = getOperation();

    EquivalenceClasses classes;

    // Step 1: Initialize classes via simulation
    initClassesViaSimulation(module, classes);

    // Step 2: Run base case (BMC from initial state)
    if (failed(runBaseCase(module, classes, kFrames, initialState)))
      return signalPassFailure();

    // Step 3: Iterative inductive refinement
    while (true) {
      if (succeeded(runInductiveCase(module, classes, kFrames)))
        break; // Converged
      // Classes were refined, loop again
    }

    // Step 4: Apply proved equivalences (merge nodes)
    applyEquivalences(module, classes);
  }
};
```

### 3.2 Add CLI Tool

```cpp
// tools/circt-kinduction/circt-kinduction.cpp
int main(int argc, char **argv) {
  // Parse command line
  // -k <depth>: induction depth
  // -c1, -c2: modules to compare
  // --init: initial state specification

  // Load MLIR
  // Run k-step induction pass
  // Report results
}
```

### 3.3 SMT Lowering

Extend existing SMT lowering to handle:
- Frame unrolling structure
- Equivalence constraints
- Counterexample extraction for refinement

## Phase 4: Testing & Optimization (Weeks 12-14)

### 4.1 Test Suite

Create comprehensive tests:

```
test/Dialect/Verif/kinduction/
├── simple-counter.mlir
├── shift-register.mlir
├── fsm-equiv.mlir
├── spec-reduction.mlir      # Test speculative reduction
├── refinement.mlir          # Test class refinement
├── multi-clock.mlir         # Multiple clock domains
└── large-design.mlir        # Scalability test
```

### 4.2 Optimizations

- [ ] Partitioning for large designs (as in ABC's lcorr)
- [ ] Incremental SAT solving
- [ ] Simulation-based filtering
- [ ] Parallel SAT queries

### 4.3 Benchmarking

Compare with:
- ABC's `ssw` command
- Yosys equivalence checking
- Commercial tools (if available)

## Phase 5: Documentation & Upstream (Weeks 15-16)

### 5.1 Documentation
- [ ] Design document explaining the algorithm
- [ ] User guide for the new tool
- [ ] API documentation

### 5.2 Upstream Contribution
- [ ] Clean up code for CIRCT coding standards
- [ ] Create RFC for CIRCT community
- [ ] Submit pull request
- [ ] Address review feedback

## File Structure

```
circt/
├── include/circt/Dialect/Verif/
│   ├── VerifOps.td              # Add new operations
│   └── KStepInduction.h         # Algorithm interface
├── lib/Dialect/Verif/
│   ├── KStepInduction.cpp       # Main algorithm
│   ├── EquivalenceClasses.cpp   # Class management
│   ├── FrameUnroller.cpp        # Frame unrolling
│   └── SpeculativeReduction.cpp # Speculative reduction
├── lib/Conversion/VerifToSMT/
│   └── KInductionToSMT.cpp      # SMT encoding
└── tools/circt-kinduction/
    └── circt-kinduction.cpp     # CLI tool
```

## Dependencies

- CIRCT (latest main branch)
- LLVM/MLIR
- Z3 SMT solver
- Python 3 (for prototyping)

## Milestones

| Milestone | Target Date | Deliverable |
|-----------|-------------|-------------|
| M1: Foundation | Week 3 | Extended Python prototype with seq support |
| M2: Core Algorithm | Week 8 | Working k-step induction in CIRCT |
| M3: Integration | Week 11 | `circt-kinduction` tool |
| M4: Testing | Week 14 | Full test suite, benchmarks |
| M5: Upstream | Week 16 | Pull request to CIRCT |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CIRCT API changes | Medium | Pin to specific CIRCT version |
| SMT solver performance | High | Implement partitioning early |
| Complex equivalence refinement | Medium | Start with simple cases |
| Large design scalability | High | Follow ABC's optimizations |

## References

1. Mishchenko et al., "Scalable and Scalably-Verifiable Sequential Synthesis"
2. ABC source code: `src/proof/ssw/`
3. CIRCT documentation: https://circt.llvm.org/
4. CIRCT BMC implementation: `circt/tools/circt-bmc/`
