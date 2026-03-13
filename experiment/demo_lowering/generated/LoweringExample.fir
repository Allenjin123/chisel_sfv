FIRRTL version 3.3.0
circuit LoweringExample :
  module LoweringExample : @[src/main/scala/LoweringExample.scala 18:7]
    input clock : Clock @[src/main/scala/LoweringExample.scala 18:7]
    input reset : UInt<1> @[src/main/scala/LoweringExample.scala 18:7]
    output io : { flip narrow : UInt<8>, flip wide : UInt<16>, flip coeff : UInt<8>, out1 : UInt<16>, out2 : UInt<16>} @[src/main/scala/LoweringExample.scala 19:14]

    node _sum_T = add(io.narrow, io.wide) @[src/main/scala/LoweringExample.scala 27:24]
    node sum = tail(_sum_T, 1) @[src/main/scala/LoweringExample.scala 27:24]
    node prod = mul(io.narrow, io.coeff) @[src/main/scala/LoweringExample.scala 28:24]
    connect io.out1, sum @[src/main/scala/LoweringExample.scala 30:11]
    connect io.out2, prod @[src/main/scala/LoweringExample.scala 31:11]

