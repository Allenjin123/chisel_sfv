FIRRTL version 3.3.0
circuit ConstFoldExample :
  module ConstFoldExample : @[src/main/scala/ConstFoldExample.scala 16:7]
    input clock : Clock @[src/main/scala/ConstFoldExample.scala 16:7]
    input reset : UInt<1> @[src/main/scala/ConstFoldExample.scala 16:7]
    output io : { flip x : UInt<8>, flip y : UInt<8>, out : UInt<16>} @[src/main/scala/ConstFoldExample.scala 17:14]

    node term1 = mul(io.x, UInt<8>(0h3)) @[src/main/scala/ConstFoldExample.scala 26:20]
    node term2 = mul(io.y, UInt<8>(0h0)) @[src/main/scala/ConstFoldExample.scala 27:20]
    node _result_T = add(term1, term2) @[src/main/scala/ConstFoldExample.scala 28:22]
    node result = tail(_result_T, 1) @[src/main/scala/ConstFoldExample.scala 28:22]
    connect io.out, result @[src/main/scala/ConstFoldExample.scala 30:10]

