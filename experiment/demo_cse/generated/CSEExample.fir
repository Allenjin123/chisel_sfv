FIRRTL version 3.3.0
circuit CSEExample :
  module CSEExample : @[src/main/scala/CSEExample.scala 5:7]
    input clock : Clock @[src/main/scala/CSEExample.scala 5:7]
    input reset : UInt<1> @[src/main/scala/CSEExample.scala 5:7]
    output io : { flip a : UInt<8>, flip b : UInt<8>, flip c : UInt<8>, out1 : UInt<16>, out2 : UInt<16>, out3 : UInt<16>} @[src/main/scala/CSEExample.scala 6:14]

    node x = mul(io.a, io.b) @[src/main/scala/CSEExample.scala 15:16]
    node y = mul(io.b, io.c) @[src/main/scala/CSEExample.scala 16:16]
    connect io.out1, x @[src/main/scala/CSEExample.scala 18:11]
    connect io.out2, y @[src/main/scala/CSEExample.scala 19:11]
    node _io_out3_T = add(x, y) @[src/main/scala/CSEExample.scala 20:16]
    node _io_out3_T_1 = tail(_io_out3_T, 1) @[src/main/scala/CSEExample.scala 20:16]
    connect io.out3, _io_out3_T_1 @[src/main/scala/CSEExample.scala 20:11]

