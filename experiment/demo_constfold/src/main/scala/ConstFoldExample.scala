package demo

import chisel3._

// Inspired by MLIR upstream #75415 saga (fused loc → OOM → erase to Unknown).
// A FIR filter tap with a zero coefficient: the entire multiply-accumulate
// chain folds away, erasing all intermediate source locations.
//
// Chisel source has 3 distinct operations:
//   line 17: term1 = io.x * coeff1    (multiply)
//   line 18: term2 = io.y * coeff2    (multiply — folds to 0)
//   line 19: result = term1 + term2   (add — folds to term1)
//
// After constant folding, only term1 survives. Lines 18 and 19 vanish
// from the optimized annotations entirely.
class ConstFoldExample extends Module {
  val io = IO(new Bundle {
    val x = Input(UInt(8.W))
    val y = Input(UInt(8.W))
    val out = Output(UInt(16.W))
  })

  val coeff1 = 3.U(8.W)
  val coeff2 = 0.U(8.W)

  val term1 = io.x * coeff1
  val term2 = io.y * coeff2
  val result = term1 + term2

  io.out := result
}

object ConstFoldExampleFIRRTL extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new ConstFoldExample())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/ConstFoldExample.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/ConstFoldExample.fir")
}
