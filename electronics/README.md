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
pre-commit hooks never rewrite the KiCad text files in here.

---

## Layout

```
electronics/
  README.md      this file — orientation + how to open
  LICENSE        CERN-OHL-P-2.0 (governs everything under electronics/)
  scratch/       freeform, non-authoritative experimentation (see scratch/README.md)
  pcbs/          one subfolder per physical board (see pcbs/README.md)
  libraries/     shared symbols, footprints, and 3D models used across PCBs
```

- **`scratch/`** — sketches and one-off experiments. Nothing in here is
  authoritative; see `scratch/README.md`.
- **`pcbs/`** — the design source of record for every fabricated board, one
  subfolder per PCB. See `pcbs/README.md` for the rev-lifecycle, promotion,
  naming, and fab-tag conventions.
- **`libraries/`** — shared KiCad symbol libraries, footprint libraries, and 3D
  models referenced by more than one PCB, so a shared part is edited in one
  place rather than duplicated per board.

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

This project's KiCad design files are pinned to **KiCad 10.0.4** (the latest
stable KiCad 10.x release as of this writing). Install that specific version
to open any files in this tree without triggering an on-open project upgrade.

> **Note:** no maintainer input was available when this scaffold was created —
> confirm 10.0.4 against the KiCad version the maintainer actually runs, and
> bump this line deliberately (with a comment on why) whenever the project
> upgrades.

Once a board exists, open its `pcbs/<pcb>/rev<X>/<pcb>.kicad_pro` project file
in KiCad — schematic and PCB editors are reached from there.
