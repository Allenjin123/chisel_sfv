// Combined IR for signal correspondence verification
// Path 1: Chisel → FIRRTL → hw (with Chisel source locations)
// Path 2: Verilog → hw (with Verilog source locations)

module {
  hw.module @Combined(
    in %clock : i1,
    in %reset : i1,
    in %io_in0 : i8,
    in %io_in1 : i8,
    in %io_in4 : i8,
    in %io_in8 : i8,
    out out_chisel : i16,
    out out_verilog : i16
  ) {
    // =========================================================================
    // PATH 1: CHISEL (from FIRRTL)
    // Source: src/main/scala/Figure5Example.scala
    // Prefix: c_
    // =========================================================================
    %c_false = hw.constant false              // loc: scala:25:71
    %c_neg1_i16 = hw.constant -1 : i16        // loc: scala:25:57
    %c_zero_i8 = hw.constant 0 : i8           // loc: scala:22:20

    // op5 = io_in0 * io_in8 (zero-extended) - loc: scala:22:20
    %c_0 = comb.concat %c_zero_i8, %io_in0 : i8, i8
    %c_1 = comb.concat %c_zero_i8, %io_in8 : i8, i8
    %c_2 = comb.mul %c_0, %c_1 : i16          // c_op5

    // VecInit elements (zero-extended) - loc: scala:25:24
    %c_3 = comb.concat %c_zero_i8, %io_in0 : i8, i8
    %c_4 = comb.concat %c_zero_i8, %io_in1 : i8, i8
    %c_5 = comb.concat %c_zero_i8, %io_in4 : i8, i8

    // NOT operations: map((x) => (~x)) - loc: scala:25:57
    %c_6 = comb.xor %c_3, %c_neg1_i16 : i16   // ~wire0
    %c_7 = comb.xor %c_4, %c_neg1_i16 : i16   // ~wire1
    %c_8 = comb.xor %c_5, %c_neg1_i16 : i16   // ~wire2
    %c_9 = comb.xor %c_2, %c_neg1_i16 : i16   // ~op5

    // reduce(_ + _) with truncation - loc: scala:25:71
    %c_10 = comb.concat %c_false, %c_6 : i1, i16
    %c_11 = comb.concat %c_false, %c_7 : i1, i16
    %c_12 = comb.add %c_10, %c_11 : i17
    %c_13 = comb.extract %c_12 from 0 : (i17) -> i16

    %c_14 = comb.concat %c_false, %c_13 : i1, i16
    %c_15 = comb.concat %c_false, %c_8 : i1, i16
    %c_16 = comb.add %c_14, %c_15 : i17
    %c_17 = comb.extract %c_16 from 0 : (i17) -> i16

    %c_18 = comb.concat %c_false, %c_17 : i1, i16
    %c_19 = comb.concat %c_false, %c_9 : i1, i16
    %c_20 = comb.add %c_18, %c_19 : i17
    %c_21 = comb.extract %c_20 from 0 : (i17) -> i16  // c_mapred6

    // =========================================================================
    // PATH 2: VERILOG (direct from .sv)
    // Source: generated/Figure5Example.sv
    // Prefix: v_
    // =========================================================================
    %v_neg1_i16 = hw.constant -1 : i16        // loc: sv:14:7
    %v_zero_i8 = hw.constant 0 : i8           // loc: sv:14:10
    %v_neg1_i8 = hw.constant -1 : i8          // loc: sv:13:6

    // ~io_in0 sign-extended - loc: sv:13:13, sv:13:5
    %v_0 = comb.xor %io_in0, %v_neg1_i8 : i8
    %v_1 = comb.concat %v_neg1_i8, %v_0 : i8, i8

    // ~io_in1 sign-extended - loc: sv:13:32, sv:13:24
    %v_2 = comb.xor %io_in1, %v_neg1_i8 : i8
    %v_3 = comb.concat %v_neg1_i8, %v_2 : i8, i8

    // ~io_in4 sign-extended - loc: sv:13:51, sv:13:43
    %v_4 = comb.xor %io_in4, %v_neg1_i8 : i8
    %v_5 = comb.concat %v_neg1_i8, %v_4 : i8, i8

    // io_in0 * io_in8 (zero-extended) - loc: sv:14:9
    %v_6 = comb.concat %v_zero_i8, %io_in0 : i8, i8
    %v_7 = comb.concat %v_zero_i8, %io_in8 : i8, i8
    %v_8 = comb.mul %v_6, %v_7 : i16          // v_mul (corresponds to c_op5)

    // ~(mul result) - loc: sv:14:7
    %v_9 = comb.xor %v_8, %v_neg1_i16 : i16   // v_not_mul (corresponds to c_9)

    // 4-way add (optimized) - loc: sv:13:5
    %v_10 = comb.add %v_1, %v_3, %v_5, %v_9 : i16  // v_result

    // =========================================================================
    // OUTPUTS
    // =========================================================================
    hw.output %c_21, %v_10 : i16, i16
  }
}
