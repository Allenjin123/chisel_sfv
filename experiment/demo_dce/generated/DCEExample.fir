FIRRTL version 3.3.0
circuit DCEExample :
  module DCEExample : @[src/main/scala/DCEExample.scala 14:7]
    input clock : Clock @[src/main/scala/DCEExample.scala 14:7]
    input reset : UInt<1> @[src/main/scala/DCEExample.scala 14:7]
    output io : { flip inc : UInt<1>, flip dec : UInt<1>, count : UInt<4>, zero : UInt<1>} @[src/main/scala/DCEExample.scala 15:14]

    regreset counter : UInt<4>, clock, reset, UInt<4>(0h0) @[src/main/scala/DCEExample.scala 22:24]
    node _incVal_T = add(counter, UInt<1>(0h1)) @[src/main/scala/DCEExample.scala 24:24]
    node incVal = tail(_incVal_T, 1) @[src/main/scala/DCEExample.scala 24:24]
    node _decVal_T = sub(counter, UInt<1>(0h1)) @[src/main/scala/DCEExample.scala 25:24]
    node decVal = tail(_decVal_T, 1) @[src/main/scala/DCEExample.scala 25:24]
    when io.inc : @[src/main/scala/DCEExample.scala 27:16]
      connect counter, incVal @[src/main/scala/DCEExample.scala 28:13]
    else :
      when io.dec : @[src/main/scala/DCEExample.scala 29:22]
        connect counter, decVal @[src/main/scala/DCEExample.scala 30:13]
    connect io.count, counter @[src/main/scala/DCEExample.scala 33:12]
    node _io_zero_T = eq(counter, UInt<1>(0h0)) @[src/main/scala/DCEExample.scala 34:23]
    connect io.zero, _io_zero_T @[src/main/scala/DCEExample.scala 34:12]

