# PCBs

The design source of record for every fabricated Aura board — one subfolder per
physical PCB.

## PCB naming

A **PCB** is the design source for **one physical board**, named for the board
itself (e.g. `wand-driver`, `target-sensor`) — never for the prop it lives
inside. Props and PCBs are a **many-to-many** relationship: one prop can carry
several boards, and the same board design can be reused across several props.
Because of that, PCBs never nest under a prop folder — they're siblings under
`pcbs/`, addressed by board name only.

## Layout

```
pcbs/
  <pcb>/
    rev<X>/
      <pcb>.kicad_pro
      <pcb>.kicad_sch
      <pcb>.kicad_pcb
      exports/
        <pcb>-rev<X>-schematic.pdf
        <pcb>-rev<X>-render.png
        <pcb>-rev<X>-bom.csv
        gerbers/
```

- `<pcb>/` — one per physical board, named for the board.
- `rev<X>/` — one per physical spin of that board (`rev1`, `rev2`, …).
- `<pcb>.kicad_pro` / `.kicad_sch` / `.kicad_pcb` — the KiCad project,
  schematic, and board layout files for that revision.
- `exports/` — hand-generated, human-facing artifacts derived from the design:
  schematic PDF, board render PNG, BOM CSV, and gerbers for fab.

## Revision lifecycle

A `rev<X>/` folder is created **once**, at the moment a design graduates from
`scratch/` (see `../scratch/README.md`) into a real, intended board. From that
point on, `rev<X>/` is the working directory across the entire cycle for that
revision:

```
design → fab → bring-up → test
```

The folder is not re-created or forked mid-cycle — ongoing edits during
bring-up and test happen in place within the same `rev<X>/`.

## Promotion

Promotion is the move from freeform `scratch/` experimentation into a
committed `pcbs/<pcb>/rev<X>/` folder. It marks the point where a design is
no longer just an idea — it's the thing that's going to be built. Before
promotion, nothing is expected to be stable; after promotion, the `rev<X>/`
folder is the authoritative source for that revision.

## Fab tags

When a revision's design is sent to fabrication, the commit representing
exactly what was sent is marked with a git tag:

```
<pcb>-rev<X>
```

The tag — not folder immutability — is what records exactly what was
fabricated. Nothing prevents further edits to `rev<X>/` after a fab tag (e.g.
fixing a documentation error, refreshing exports), but a genuinely new
physical spin of the board is always a **new** `rev<X+1>/` folder, tagged
separately when it, in turn, goes to fab.

## Exports

Exports under `rev<X>/exports/` are **hand-generated**, not build artifacts —
regenerate and commit them whenever the design changes, and refresh them
again at each fab tag so they match what was actually built.
