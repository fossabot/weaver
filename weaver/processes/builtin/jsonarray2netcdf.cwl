#!/usr/bin/env cwl-runner
cwlVersion: v1.0
class: CommandLineTool
baseCommand: python
arguments: ["-m", "weaver.processes.builtin.jsonarray2netcdf", $(runtime.outdir)]
inputs:
 input:
   type: File
   format: iana:application/json
   inputBinding:
     position: 1
outputs:
 output:
   format: edam:format_3650
   type:
     type: array
     items: File
   outputBinding:
     glob: "*.nc"
$namespaces:
  iana: "https://www.iana.org/assignments/media-types/"
  edam: "http://edamontology.org/"
