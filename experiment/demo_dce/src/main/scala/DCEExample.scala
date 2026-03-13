package demo

import chisel3._
import chisel3.util._

// Inspired by CIRCT #2733 (VendingMachine location contamination).
// A counter with increment/decrement: both paths share the counter
// register operand. After lowering, zero-extension of `counter` is
// CSE'd, and one branch's location leaks into the other's annotation.
//
// This is the same mechanism that caused SimpleVendingMachine.scala
// locations to appear in ImplicitStateVendingMachine.scala output
// in the original bug report.
class DCEExample extends Module {
  val io = IO(new Bundle {
    val inc   = Input(Bool())
    val dec   = Input(Bool())
    val count = Output(UInt(4.W))
    val zero  = Output(Bool())
  })

  val counter = RegInit(0.U(4.W))

  val incVal = counter + 1.U
  val decVal = counter - 1.U

  when(io.inc) {
    counter := incVal
  }.elsewhen(io.dec) {
    counter := decVal
  }

  io.count := counter
  io.zero  := counter === 0.U
}

object DCEExampleFIRRTL extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new DCEExample())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/DCEExample.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/DCEExample.fir")
}
