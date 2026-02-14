package demo

import chisel3._
import chisel3.util._

// Figure 5 Chisel Code 1 from CHIVAL paper
class Figure5Example extends Module {
  val io = IO(new Bundle {
    val in0 = Input(UInt(8.W))
    val in1 = Input(UInt(8.W))
    val in4 = Input(UInt(8.W))
    val in8 = Input(UInt(8.W))
    val out0 = Output(UInt(16.W))
  })

  // Intermediate signals (op0, op1, op2, op4 from other operations)
  val op0 = io.in0
  val op1 = io.in8*io.in4
  val op2 = io.in1+io.in4
  val op4 = io.in4*io.in1

  // op5 := io.in0 * io.in8
  val op5 = io.in0 * io.in8

  // mapred6 := VecInit(op0,op1,op2,op4,op5).map((x) => (~x)).reduce(_ + _)
  val mapred6 = VecInit(op0, op1, op2, op4, op5).map((x) => (~x)).reduce(_ + _)

  // io.out0 := mapred6
  io.out0 := mapred6
}

// Generate FIRRTL
object Figure5ExampleFIRRTL extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new Figure5Example())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/Figure5Example.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/Figure5Example.fir")
}

// Generate Verilog (with optimization - normal usage)
object Figure5ExampleVerilog extends App {
  val verilog = _root_.circt.stage.ChiselStage.emitSystemVerilog(new Figure5Example())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/Figure5Example.sv"))
  writer.write(verilog)
  writer.close()
  println("Verilog written to generated/Figure5Example.sv")
}
