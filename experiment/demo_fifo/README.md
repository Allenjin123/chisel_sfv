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

### 验证脚本
- **yosys_equiv.ys** - 全模块时序等价性检查（Yosys）
- **trace_expr2.ys** - 表达式追踪（Yosys）
- **prove_correspondence.py** - 信号对应关系验证（Z3）

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

### 4. 验证时序等价性
```bash
yosys yosys_equiv.ys
```

### 5. 追踪表达式
```bash
yosys trace_expr2.ys
```

### 6. 使用 Z3 验证信号对应关系（可选）
```bash
# 需要先激活 conda 环境并安装 z3-solver
conda activate sfv
pip install z3-solver

# 运行 Python 验证脚本
python prove_correspondence.py
```

**注意**: 对于时序电路，Python 脚本只能验证组合逻辑部分（如控制信号的布尔表达式）。完整的时序等价性验证（包括状态转换）需要使用 Yosys 的 `equiv_induct`。

## 验证工具的区别

### yosys_equiv.ys - 全模块时序等价性检查
- **目的**: 验证优化前后整个时序电路功能完全等价
- **特点**:
  - 使用 `equiv_induct` 进行归纳法证明（时序电路专用）
  - 展平模块层次结构以便比较
  - 验证所有寄存器和组合逻辑的等价性
- **使用场景**: 确保优化没有改变 FIFO 的时序行为
- **输出**: 显示所有匹配的信号对和最终验证状态

### trace_expr2.ys - 表达式追踪（时序电路）
- **目的**: 找出优化后的信号对应未优化版本中的哪些信号
- **特点**:
  - 可以追踪特定的寄存器（如 `stateReg`, `dataReg`）
  - 可以追踪控制信号（如 `io_enq_ready`, `io_deq_valid`）
  - 时序电路的追踪比组合电路更复杂
- **使用场景**: 理解优化后的状态机和寄存器对应的原始信号
- **输出**: 显示特定信号的对应关系

### prove_correspondence.py - Z3 信号对应验证
- **目的**: 使用 SMT 求解器验证控制信号的对应关系
- **特点**:
  - 从 Verilog 文件中提取信号定义
  - 使用 Z3 进行符号化验证
  - 只能验证组合逻辑部分
- **使用场景**: 快速验证特定控制信号的等价性
- **限制**: 不能处理完整的状态机转换，需要配合 Yosys 使用

## 电路说明

### Double Buffer FIFO 设计

这是一个高吞吐量的 FIFO 设计，每个双缓冲级有：

**状态机（3个状态）：**
- `empty`: FIFO 为空
- `one`: 有一个数据在 `dataReg` 中
- `two`: 有两个数据（`dataReg` + `shadowReg`）

**寄存器：**
- `stateReg`: 当前状态
- `dataReg`: 主数据寄存器
- `shadowReg`: 影子寄存器（当下游满时存储额外数据）

**控制逻辑：**
- `io.enq.ready = (state == empty || state == one)`: 可以接受新数据
- `io.deq.valid = (state == one || state == two)`: 有数据可以输出

### 时序等价性验证的特殊性

与组合电路不同，时序电路的验证需要：
1. **归纳证明**（`equiv_induct`）：证明如果初始状态相同，则所有后续状态都相同
2. **展平层次**（`flatten`）：将模块实例化展开为单一层次
3. **考虑时钟和复位**：确保时序行为一致

### 未优化 vs 优化版本

**未优化版本**可能包含：
- 所有中间状态比较信号（`_GEN`, `_GEN_0`, `_GEN_1` 等）
- 显式的状态转换逻辑
- 命名的中间线网

**优化版本**可能：
- 合并状态比较表达式
- 简化状态转换逻辑
- 移除冗余信号

Yosys 验证这两个版本在功能上完全等价，即对于相同的输入序列，产生相同的输出序列。

## 与组合电路示例（demo）的区别

| 特性 | demo (组合电路) | demo_fifo (时序电路) |
|------|----------------|---------------------|
| **电路类型** | 纯组合逻辑 | 状态机 + 寄存器 |
| **验证方法** | `equiv_simple` | `equiv_induct` + `equiv_simple` |
| **信号追踪** | 简单，直接表达式映射 | 复杂，需要考虑状态 |
| **模块层次** | 单模块 | 多层次（需要 `flatten`） |
| **验证难度** | 较简单 | 较复杂 |
