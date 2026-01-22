package fifo

import chisel3._
import chisel3.util._

class FifoIO[T <: Data](gen: T) extends Bundle {
  val enq = Flipped(new DecoupledIO(gen))
  val deq = new DecoupledIO(gen)
}

abstract class Fifo[T <: Data](gen: T, depth: Int) extends Module {
  val io = IO(new FifoIO(gen))
}

/**
  * Double buffer FIFO.
  * Maximum throughput is one word per clock cycle.
  * Each stage has a shadow buffer to handle the downstream full.
  */
class DoubleBufferFifo[T <: Data](gen: T, depth: Int) extends Fifo(gen: T, depth: Int) {

  private class DoubleBuffer[T <: Data](gen: T) extends Module {
    val io = IO(new FifoIO(gen))

    val empty :: one :: two :: Nil = Enum(3)
    val stateReg = RegInit(empty)
    val dataReg = Reg(gen)
    val shadowReg = Reg(gen)

    switch(stateReg) {
      is (empty) {
        when (io.enq.valid) {
          stateReg := one
          dataReg := io.enq.bits
        }
      }
      is (one) {
        when (io.deq.ready && !io.enq.valid) {
          stateReg := empty
        }
        when (io.deq.ready && io.enq.valid) {
          stateReg := one
          dataReg := io.enq.bits
        }
        when (!io.deq.ready && io.enq.valid) {
          stateReg := two
          shadowReg := io.enq.bits
        }
      }
      is (two) {
        when (io.deq.ready) {
          dataReg := shadowReg
          stateReg := one
        }
      }
    }

    io.enq.ready := (stateReg === empty || stateReg === one)
    io.deq.valid := (stateReg === one || stateReg === two)
    io.deq.bits := dataReg
  }

  private val buffers = Array.fill((depth+1)/2) { Module(new DoubleBuffer(gen)) }

  for (i <- 0 until (depth+1)/2 - 1) {
    buffers(i + 1).io.enq <> buffers(i).io.deq
  }
  io.enq <> buffers(0).io.enq
  io.deq <> buffers((depth+1)/2 - 1).io.deq
}

// Top-level wrapper for Verilog generation (depth=4 means 2 DoubleBuffer stages)
class DoubleBufferFifoTop extends Module {
  val io = IO(new FifoIO(UInt(8.W)))
  val fifo = Module(new DoubleBufferFifo(UInt(8.W), depth = 4))
  io <> fifo.io
}

// Generate FIRRTL
object GenerateFirrtl extends App {
  val firrtl = _root_.circt.stage.ChiselStage.emitCHIRRTL(new DoubleBufferFifoTop())
  val outputDir = new java.io.File("generated")
  outputDir.mkdirs()
  val writer = new java.io.PrintWriter(new java.io.File("generated/DoubleBufferFifo.fir"))
  writer.write(firrtl)
  writer.close()
  println("FIRRTL written to generated/DoubleBufferFifo.fir")
}
