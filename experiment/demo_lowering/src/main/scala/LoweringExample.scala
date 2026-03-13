package demo

import chisel3._

// Demonstrates Section 1.3 from the research: lowering-phase type
// conversions carry parent FIRRTL op's location.
//
// When FIRRTL is lowered to HW/Comb, implicit conversions are inserted:
//   - zero-extension for width padding (narrow → wide)
//   - truncation for width narrowing
// These synthetic ops inherit their parent's location. When two
// independent FIRRTL ops share an operand needing the same padding,
// the padding is CSE'd, and one op's location contaminates the other.
//
// Here, `sum` (line 24) and `prod` (line 25) both use io.narrow,
// which needs zero-extension. The shared padding carries sum's
// location into prod's annotation.
class LoweringExample extends Module {
  val io = IO(new Bundle {
    val narrow = Input(UInt(8.W))
    val wide   = Input(UInt(16.W))
    val coeff  = Input(UInt(8.W))
    val out1 = Output(UInt(16.W))
    val out2 = Output(UInt(16.W))
  })

  val sum  = io.narrow + io.wide
  val prod = io.narrow * io.coeff

  io.out1 := sum
  io.out2 := prod
}

object LoweringExampleFIRRTL extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new LoweringExample())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/LoweringExample.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/LoweringExample.fir")
}
