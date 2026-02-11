# FIFO Example - Double Buffer FIFO with Sequential Logic

这个示例展示了一个带状态机的 FIFO（先进先出队列）实现，并使用 Yosys 进行时序电路的等价性验证。

## 文件说明

### Chisel 源码
- **src/main/scala/Fifo.scala** - Chisel 硬件描述，实现双缓冲 FIFO
  - `DoubleBuffer`: 单个双缓冲级，有三个状态（empty, one, two）
  - `DoubleBufferFifo`: 多级 FIFO
  - `DoubleBufferFifoTop`: 顶层模块（深度=4，即2个双缓冲级）

### 生成的文件
- **generated/DoubleBufferFifo.fir** - FIRRTL 中间表示
- **generated/unoptimized.sv** - 未优化的 SystemVerilog（保留所有中间信号和寄存器）
- **generated/optimized.sv** - 优化后的 SystemVerilog（可能合并逻辑）


## 使用步骤

### 1. 生成 FIRRTL
```bash
sbt "runMain fifo.GenerateFirrtl"
```

### 2. 生成未优化的 Verilog
```bash
firtool generated/DoubleBufferFifo.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  --disable-opt \
  --preserve-values=all \
  -o generated/unoptimized.sv
```

### 3. 生成优化的 Verilog
```bash
firtool generated/DoubleBufferFifo.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  -o generated/optimized.sv
```

