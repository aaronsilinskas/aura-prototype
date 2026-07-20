# Libraries

Shared KiCad symbols, footprints, and 3D models used across more than one PCB.

When a part (connector, sensor, driver IC, etc.) shows up in multiple boards under
`../pcbs/`, its symbol, footprint, and any 3D model belong here instead of being
duplicated per board — one definition, referenced by every PCB that uses the part,
so a correction or improvement only has to happen once.

Parts used by only a single PCB can stay local to that PCB's own project
libraries under `../pcbs/<pcb>/rev<X>/`; promote them here only once a second
board needs the same part.

No shared library files exist yet — this folder is intentionally empty until a
part is actually reused across boards.
