# Scratch

Freeform experimentation space for electronics design-in-progress — quick sketches,
half-finished schematics, part comparisons, wiring notes, anything that helps while
figuring out what a board should be.

**Nothing in this directory is authoritative.** Nothing here is guaranteed to be
correct, complete, buildable, or even kept up to date. A design in `scratch/` has no
fab tag, no revision folder, and no promise of a `rev<X>/` promotion.

Once a sketch here graduates into an intended real board, it is **promoted** into
`pcbs/<pcb>/rev<X>/` — at that point the `pcbs/` copy is the source of record, and
whatever is left behind in `scratch/` stays non-authoritative. See
`../pcbs/README.md` for the promotion and revision-lifecycle conventions.
