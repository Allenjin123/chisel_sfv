package demo

import chisel3._

class CSEExample extends Module {
  val io = IO(new Bundle {
    val a = Input(UInt(8.W))
    val b = Input(UInt(8.W))
    val c = Input(UInt(8.W))
    val out1 = Output(UInt(16.W))
    val out2 = Output(UInt(16.W))
    val out3 = Output(UInt(16.W))
  })

  val x = io.a * io.b
  val y = io.b * io.c

  io.out1 := x
  io.out2 := y
  io.out3 := x + y
}

object CSEExampleFIRRTL extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new CSEExample())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/CSEExample.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/CSEExample.fir")
}
