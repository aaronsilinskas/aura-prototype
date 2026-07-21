# Libraries

Shared symbols, footprints, and 3D models used across more than one PCB.

When a part (connector, sensor, driver IC, etc.) shows up in multiple boards under
`../pcbs/`, its symbol, footprint, and any 3D model belong here instead of being
duplicated per board — one definition, referenced by every PCB that uses the part,
so a correction or improvement only has to happen once.

Parts used by only a single PCB can stay local to that PCB's own project
libraries under `../pcbs/<pcb>/rev<X>/`; promote them here only once a second
board needs the same part.

## Per-tool split

This project uses two PCB tools as peers — **KiCad** and **EasyEDA Pro** — with
each board committed to a single tool (see `../pcbs/README.md`). Their library
formats are not interchangeable, so shared libraries are kept per tool:

```
libraries/
  kicad/      shared KiCad symbol/footprint/3D-model libraries
  easyeda/    shared EasyEDA Pro libraries
```

A part shared across boards drawn in the same tool gets one definition in that
tool's subfolder. A part shared across boards drawn in *different* tools needs a
definition in each subfolder — there is no cross-tool shared source, so keep the
two in sync by hand when that happens.
