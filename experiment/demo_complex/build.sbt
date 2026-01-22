ThisBuild / scalaVersion := "2.13.12"
ThisBuild / version      := "0.1.0"

lazy val root = (project in file("."))
  .settings(
    name := "complex-demo",
    libraryDependencies ++= Seq(
      "org.chipsalliance" %% "chisel" % "6.5.0",
    ),
    addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.5.0" cross CrossVersion.full),
  )
