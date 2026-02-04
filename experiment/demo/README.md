# Figure 5 Example - Chisel to Verilog with Expression Tracing

这个示例展示了如何使用 Chisel 生成 Verilog，并使用 Yosys 进行等价性验证和表达式追踪。

## 文件说明

### Chisel 源码
- **src/main/scala/Figure5Example.scala** - Chisel 硬件描述，实现 map-reduce 模式

### 生成的文件
- **generated/Figure5Example.fir** - FIRRTL 中间表示
- **generated/unoptimized.sv** - 未优化的 SystemVerilog（保留所有中间信号）
- **generated/optimized.sv** - 优化后的 SystemVerilog（合并表达式）

### Yosys 验证脚本
- **yosys_equiv.ys** - 全模块等价性检查
- **trace_expr2.ys** - 表达式追踪

## 使用步骤

### 1. 生成 FIRRTL
```bash
sbt "runMain demo.Figure5ExampleFIRRTL"
```

### 2. 生成未优化的 Verilog
```bash
firtool generated/Figure5Example.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  --disable-opt \
  --preserve-values=all \
  -o generated/unoptimized.sv
```

### 3. 生成优化的 Verilog
```bash
firtool generated/Figure5Example.fir \
  --disable-all-randomization \
  --lowering-options=disallowLocalVariables,disallowPackedArrays,locationInfoStyle=wrapInAtSquareBracket \
  -o generated/optimized.sv
```

### 4. 验证等价性
```bash
yosys yosys_equiv.ys
```

### 5. 追踪表达式
```bash
yosys trace_expr2.ys
```

## Yosys 脚本的区别

### yosys_equiv.ys - 全模块等价性检查
- **目的**: 验证优化前后整个模块功能完全等价
- **检查内容**: 验证关键信号（如 `mapred6`）在优化前后保持一致
- **使用场景**: 确保优化没有改变电路的行为
- **输出**: 显示哪些信号对被验证为等价

### trace_expr2.ys - 表达式追踪
- **目的**: 找出优化后的表达式对应未优化版本中的哪个信号
- **检查内容**: 将优化版本中的具体表达式映射回原始命名信号
- **使用场景**: 逆向工程，理解优化后的代码片段的原始含义
- **输出**: 显示表达式对应关系

## 电路说明

这个例子实现了一个 map-reduce 模式：

```scala
val mapred6 = VecInit(op0, op1, op4, op5).map((x) => (~x)).reduce(_ + _)
```

其中：
- `op0` = io.in0
- `op1` = io.in1
- `op4` = io.in4
- `op5` = io.in0 * io.in8

**未优化版本**保留了所有中间步骤：
- 各个 map 操作的结果（`_mapred6_T`, `_mapred6_T_1`, 等）
- 各个 reduce 步骤的结果（`_mapred6_T_4`, `_mapred6_T_6`, 等）
- 最终结果 `mapred6`

**优化版本**将所有逻辑合并为一个表达式：
```verilog
assign io_out0 = {8'hFF, ~io_in0} + {8'hFF, ~io_in1} + {8'hFF, ~io_in4} + ~({8'h0, io_in0} * {8'h0, io_in8});
```

Yosys 验证这两个版本在功能上完全等价。
