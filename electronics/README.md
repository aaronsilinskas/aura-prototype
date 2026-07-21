# Electronics

PCB design source for Aura's custom hardware — schematics, board layouts, shared
symbols/footprints, and fabrication exports. This directory is deliberately separate
from:

- **`hardware/`** (repo root) — the Python firmware package that runs on the props'
  microcontrollers, governed by `ruff`/`import-linter`.
- **CircuitPython's `board` module** — the on-device pin-naming API `hardware/`
  imports at runtime.

`electronics/` contains no Python and is not a package. It carries no import
contracts, isn't touched by `ruff` or `import-linter`, and the Python-only
pre-commit hooks never rewrite the PCB-tool files in here.

Boards are drawn in one of two tools, used as peers: **KiCad** and
**EasyEDA Pro**. Each PCB is committed to a single tool (never mixed within one
board); see `pcbs/README.md`.

---

## Layout

```
electronics/
  README.md      this file — orientation + how to open
  LICENSE        CERN-OHL-P-2.0 (governs everything under electronics/)
  scratch/       freeform, non-authoritative experimentation (see scratch/README.md)
  pcbs/          one subfolder per physical board (see pcbs/README.md)
  libraries/     shared symbols, footprints, and 3D models used across PCBs,
                 split per tool (see libraries/README.md)
```

- **`scratch/`** — sketches and one-off experiments. Nothing in here is
  authoritative; see `scratch/README.md`.
- **`pcbs/`** — the design source of record for every fabricated board, one
  subfolder per PCB. See `pcbs/README.md` for the rev-lifecycle, promotion,
  naming, and fab-tag conventions.
- **`libraries/`** — shared symbol libraries, footprint libraries, and 3D
  models referenced by more than one PCB, so a shared part is edited in one
  place rather than duplicated per board. Split into per-tool subfolders
  (`kicad/`, `easyeda/`) since the two tools' library formats aren't
  interchangeable.

No `<pcb>/` design folders or library files exist yet — this scaffold is
intentionally empty of actual designs.

---

## Revision lifecycle, promotion, and naming (summary)

Full detail lives in `pcbs/README.md`; the short version:

- A **PCB** is the design source for one physical board, named for the board
  itself — never for the prop it ends up in, since a prop and its PCBs are a
  many-to-many relationship (one prop can carry several boards; the same
  board design can serve several props).
- A design **promotes** from `scratch/` into `pcbs/<pcb>/rev<X>/` the moment it
  graduates from sketch to an intended real board. That `rev<X>/` folder is
  then the working directory for the whole design → fab → bring-up → test
  cycle for that revision.
- A genuinely new physical spin of a board is a **new** `rev<X>/` folder
  (`rev2`, `rev3`, …), never an edit-in-place of a prior rev.
- The **rev letter/number goes on the PCB silkscreen**, so the physical board
  and its design folder are always traceable to each other.
- The commit sent to fab is marked with a **git tag** `<pcb>-rev<X>` — the tag,
  not folder immutability, records exactly what was fabricated. Exports are
  hand-generated and refreshed at each fab tag.

---

## How to open

Which tool a board opens in follows its file extensions (`.kicad_*` vs
`.epro`); a board's own folder is drawn in exactly one tool. Tool versions are
pinned so files open without an on-open project upgrade:

- **KiCad** — pinned to **10.0.4** (the latest stable KiCad 10.x release as of
  this writing). Open `pcbs/<pcb>/rev<X>/<pcb>.kicad_pro` in KiCad; schematic
  and PCB editors are reached from there.
- **EasyEDA Pro** — pinned to **3.2**. Open the board's `pcbs/<pcb>/rev<X>/`
  EasyEDA Pro project (`.epro`) in EasyEDA Pro.

> **Note:** no maintainer input was available when this scaffold was created —
> confirm both pinned versions against what the maintainer actually runs, and
> bump these lines deliberately (with a comment on why) whenever the project
> upgrades.
