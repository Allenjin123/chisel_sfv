package demo

import chisel3._
import chisel3.util._

// More complex example with multiple multiplications
// Purpose: Demonstrate Chisel-to-Verilog signal traceability
class ComplexExample extends Module {
  val io = IO(new Bundle {
    val a = Input(UInt(8.W))
    val b = Input(UInt(8.W))
    val c = Input(UInt(8.W))
    val d = Input(UInt(8.W))
    val sel = Input(UInt(2.W))
    val out = Output(UInt(16.W))
  })

  // Multiple multiplications at different source locations
  val mul1 = io.a * io.b      // Line 19: a * b
  val mul2 = io.c * io.d      // Line 20: c * d
  val mul3 = io.a * io.c      // Line 21: a * c
  val mul4 = io.b * io.d      // Line 22: b * d

  // Intermediate computations
  val sum1 = mul1 + mul2      // Line 25: (a*b) + (c*d)
  val sum2 = mul3 + mul4      // Line 26: (a*c) + (b*d)
  val diff = mul1 - mul3      // Line 27: (a*b) - (a*c)

  // More complex expressions
  val expr1 = sum1 * 2.U      // Line 30: ((a*b) + (c*d)) * 2
  val expr2 = sum2 + diff     // Line 31: (a*c + b*d) + (a*b - a*c)

  // Mux based on selector
  val result = MuxLookup(io.sel, 0.U)(Seq(
    0.U -> sum1,              // Line 35
    1.U -> sum2,              // Line 36
    2.U -> expr1,             // Line 37
    3.U -> expr2              // Line 38
  ))

  io.out := result
}

// Generate FIRRTL
object GenerateFirrtl extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new ComplexExample())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/ComplexExample.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/ComplexExample.fir")
}
