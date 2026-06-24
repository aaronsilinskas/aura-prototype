# deploy-watch skill

Use this skill whenever you need to deploy a CircuitPython example to the device and
capture or interpret its serial output — including profiling runs, hardware tests, or
any time you want to observe what the device prints after a deploy.

---

## Invocation

Always run as a module from the repo root (direct `python scripts/deploy_watch.py`
fails with an import error):

```
python -m scripts.deploy_watch <example_file> [options]
```

At least one of `--seconds` or `--until` is required.

## Key flags

| Flag | Purpose |
|---|---|
| `--seconds N` | Stop after N seconds of serial output |
| `--until TEXT` | Stop as soon as any output line contains TEXT (exit 0) |
| `--output FILE` | Also write clean device output to FILE (no deploy chatter) |
| `--port PORT` | Serial port; auto-detected from `/dev/tty.usbmodem*` if omitted |
| `--reboot-timeout N` | Seconds to wait for the CircuitPython soft-reboot banner (default 5) |

Both `--seconds` and `--until` can be combined: exits 0 on match, 2 on timeout.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Matched (`--until` found), or timed out / stream ended without `--until` |
| 1 | Usage error or port-discovery failure |
| 2 | Timed out before `--until` marker was matched |
| 3 | CircuitPython soft-reboot banner never appeared within `--reboot-timeout` |

## Output anatomy

```
COPY  code.py          ← deploy phase (one line per file copied)
SKIP  effects/...      ← deploy phase (files already up to date)
Done. 1 copied, 185 skipped, 0 pruned.
                       ← script waits for "soft reboot" banner here
[device serial output] ← everything after the banner is captured
```

The `--output FILE` flag captures only the post-banner device lines — no deploy
chatter — which is useful for parsing profiler output in a subsequent step.

## Common patterns

**Profiling run (fixed time window):**
```
python -m scripts.deploy_watch examples/hardware/profiling/baseline_profiler.py --seconds 30
```

**Wait for a specific marker:**
```
python -m scripts.deploy_watch examples/hardware/profiling/baseline_profiler.py \
    --until "__PROFILE" --seconds 15
```

**Capture clean output to file for later analysis:**
```
python -m scripts.deploy_watch examples/hardware/profiling/baseline_profiler.py \
    --seconds 30 --output /tmp/profile_run.txt
```

## Interpreting profiler output

Lines prefixed with `__PROFILE` are emitted once at startup and describe the run
configuration (component, board, firmware version, free memory).

Lines prefixed with `__STATS` are periodic snapshots with FPS, update/render time,
memory usage, and CPU percent.

Lines prefixed with `__TABLE_ROW` contain pipe-delimited data rows intended for
aggregation into comparison tables.

## Troubleshooting

- **Exit 3 / banner never seen** — the device may be hung or failed to reload;
  try a manual reset or increase `--reboot-timeout`.
- **Exit 1 / no port found** — device not connected or not mounted; use `--port`
  to specify manually.
- **Exit 1 / multiple ports** — more than one usbmodem device detected; use
  `--port /dev/tty.usbmodem<id>` to disambiguate.
