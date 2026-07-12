# Recorded Hardware Metrics

Direct measurements recorded on real hardware. Each number here is a recording that is
true in isolation — a whole-prop measurement of an assembled prop, or a per-component
CPU-cost term that is genuinely measurable for that component on its own.

These are recordings, **not** a predictive model. Nothing here is meant to be summed or
composed to forecast a different configuration: a whole-prop figure is authoritative for
*that* assembled prop regardless of how it decomposes, and a per-component CPU term is the
measured cost of running *that* component. Combining them to estimate an unmeasured prop
is out of scope.

Constants are keyed by `(board, runtime, driver)`. Cells that hardware could not measure
(e.g. an IR-rx deadline with no external packet source) carry `_TBD_`.

See [`calibration-guide.md`](calibration-guide.md) for how each table is produced and read
on hardware.

---

## Whole-prop measurements

Direct measurements of fully assembled props on the board. These are authoritative for the
assembled prop as measured.

### Reference `tag` prop

The reference prop is the **Adafruit RP2040 PropMaker Feather running the `tag` scene**:
an IS31FL3741 matrix with all scopes composited on the one matrix, I2S audio, DRV2605L
vibration, one IR LINE emitter + one IR receiver, two buttons, and an LIS3DH accelerometer
— a single-MCU prop.

The matrix `flush_ms` (~60.69 ms, see pixel-scope costs below) alone busts the 24 FPS
budget, so this prop's achievable single-MCU rate is **~7.9 FPS**. The figures below were
recorded at a **7 FPS** target (142.9 ms frame budget). Recorded at `num_voices = 4`.

| Board | Runtime | Driver | CPU reservation | Total heap footprint | Headroom | Peak frame |
|-------|---------|--------|-----------------|----------------------|----------|------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 60.41% | 32,608 B | 13.94% | 150.88 ms |

The total heap footprint (32,608 B) and peak frame time (150.88 ms) are whole-prop
recordings of the assembled `tag` prop — authoritative as measured, independent of any
per-component breakdown.

---

## Per-component CPU costs

Per-frame / per-event CPU cost terms, each measured for a single component in isolation.
These are genuinely measurable per component (a per-pixel slope, a flush intercept, a
per-event cost). Slopes and intercepts are fit on-device over the relevant sweep.

### Engine component costs

Per-tick cost terms scaling with rules, events, and remote MCUs.

| Board | Runtime | Driver | `tick_fixed_ms` | `per_rule_ms` | `per_event_ms` | `router_overhead_ms` |
|-------|---------|--------|------------------|----------------|-----------------|------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.0694 | 0.0621 | 0.1177 | _TBD_ |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.1728 | 0.0565 | 0.1147 | _TBD_ |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | - | 0.1646 | 0.0390 | 0.1178 | _TBD_ |

`tick_fixed_ms` is the `(0 rules, 0 events)` point — the same rule-less tick the
engine-host baseline measures, so the two overlap. `router_overhead_ms` (per-remote-MCU
command/event overhead) has no in-tick seam to profile yet, so it stays `_TBD_`.

The `per_rule_ms` / `per_event_ms` slopes are each measured at a cross-load of 1 (the other
axis held at 1). The real dispatch loop is `O(events × rules)`, so these slopes are
measured at the low-cross-load corner and should not be extrapolated as if independent at
high simultaneous load.

### Pixel scope costs

Per-frame render+flush terms, keyed by driver. The `linear_fit` slope is
`worst_case_effect_per_pixel_ms`; the intercept is `flush_ms`. `effect_manager.update`
renders and flushes in one call, so `flush_ms` falls out as the fixed intercept.

| Board | Runtime | Driver | `worst_case_effect_per_pixel_ms` | `flush_ms` | `i2c_bandwidth_bytes_per_sec` |
|-------|---------|--------|----------------------------------|------------|-------------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | neopixel_pwm | 0.523107 | 5.9815 | 0.0 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | is31fl3741_matrix | 0.103225 | 59.2329 | 8664.0 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | neopixel_pwm | 0.551999 | 5.8358 | 0.0 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | is31fl3741_matrix | 0.105998 | 60.6856 | 8664.0 |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | neopixel_pwm | 0.103039 | 12.8649 | 0.0 |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | is31fl3741_matrix | 0.022895 | 44.4505 | 8664.0 |

NeoPixel PWM is off the I2C bus (reports 0); the buffered matrix flush is the dominant I2C
consumer. The matrix `flush_ms` (~60.69 ms) alone exceeds the 24 FPS budget (41.7 ms),
which is why any IS31FL3741 scope tops out near 10–12 FPS regardless of pixel count.

Provenance: both drivers are now the production outputs (`IS31FL3741EffectOutput` /
`NeoPixelEffectOutput`) built through `build_hardware`, not the profiler's former local
wrappers. The NeoPixel row's `flush_ms` is now the **constant max-length `show()` cost**:
the strip is built once at the largest swept count and `neopixel.show()` always clocks the
full physical strip, so `worst_case_effect_per_pixel_ms` reflects render only, not per-pixel
clock-out (a conservative approximation that never under-reports flush).

### Sound component costs

Per-frame mixer terms. The `linear_fit` intercept is `mixer_fixed_ms`; the slope is
`per_voice_ms`.

| Board | Runtime | Driver | `mixer_fixed_ms` | `per_voice_ms` |
|-------|---------|--------|------------------|----------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.1834 | 0.0521 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.1929 | 0.0425 |

### Vibration component costs

Per-event cost for the shared DRV2605L haptic motor.

| Board | Runtime | Driver | `cost_ms` | `i2c_bandwidth_bytes_per_sec` |
|-------|---------|--------|-----------|-------------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 7.4870 | 1.80 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 7.0801 | 1.80 |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | - | 5.8187 | 1.80 |

`cost_ms` is the measured average per-event CPU cost of `handle_event` + `motor.play()`.
The DRV2605L is called at a low rate (≤6 calls/min on the reference prop), so its amortized
per-frame share is well under this per-event figure.

### IR-transmit component costs

`blocking_send_ms` is the realistic 4-byte AURA payload's `PulseOut.send` blocking
duration. The worst-case across the full payload sweep (longest payload) is ~757.81 ms —
use that only for much longer payloads. `cost_ms` is the average per-frame reservation at
the AURA cadence (one 4-byte packet / 5 s → `send_rate_hz = 0.2` at 24 FPS ≈ 0.50 ms).

| Board | Runtime | Driver | `cost_ms` | `blocking_send_ms` |
|-------|---------|--------|-----------|--------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.50 | 59.81 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.50 | 59.57 |

### IR-receive component deadline

The IR receiver is hard-real-time: `max_frame_ms` is the longest a frame can take before
the `PulseIn` buffer overflows and data is dropped, keyed additionally by `buffer_depth`
(`PulseIn.maxlen`) and `incoming_rate_hz`. Measuring it requires an external IR packet
source; on a bare board no packets arrive and `max_frame_ms` is `_TBD_`.

| Board | Runtime | Driver | `buffer_depth` | `incoming_rate_hz` | `max_frame_ms` |
|-------|---------|--------|----------------|--------------------|----------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 64 | 13.91 | 58.59 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 64 | 13.9 | 63.01 |

---

## Board profiles

Per-board whole-board heap measurement. `total_free_heap_bytes` is the profiler's
`gc.mem_free()` reading on the bare framework. `target_fps` (24 ceiling) and
`headroom_reserve_percent` (20% default) are config inputs, not recordings.

| Board | Runtime | Driver | `target_fps` | `total_free_heap_bytes` | `headroom_reserve_percent` |
|-------|---------|--------|--------------|-------------------------|------------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 24 | 130576 | 20% |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 24 | 129536 | 20% |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | - | 24 | 8277264 | 20% |

### Per-MCU baseline CPU

The fixed CPU each role's bare framework loop consumes before any component work.
`engine-host` profiles the rule-less `GameEngine.update(state)` tick; `satellite` profiles
the bare framework loop with no engine.

| Board  | Runtime | Driver | Role | `cpu_percent` |
|--------|---------|--------|------|---------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | engine-host | 4.75% |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | satellite | 4.50% |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | engine-host | 5.65% |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | satellite | 5.21% |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | - | engine-host | 7.18% |
| pimoroni_pico_plus2w | circuitpython_10_2_1 | - | satellite | 6.68% |

---

## Per-scene in-situ baselines

Per-scene heap measured **in situ** on the deployed prop by
[`scene_load_profiler.py`](../../examples/hardware/profiling/scene_load_profiler.py): the
profiler builds its prop entirely from the deployed `aura-device.json` (via
`read_device_config_mapping` → `parse_device_config` → `build_hardware`, the same
config-driven seam `run_scene` uses), loads the scene named by the config's `"scene"` key
against those real outputs (whichever pixels/audio/IR sections the config declares), and
reports the staged heap it retains. The two columns below are split into a staged `load` Δ
(the heap `SceneManager.load` retains) and a first-tick Δ (the heap the first
`SceneManager.update` retains, when the scene's opening effects fire) — both measured
*after* the coarser hardware-bundle / registry-scan / engine-construction stages the
profiler's `__SCENE_STAGES` line reports separately. The near-zero `load` Δ across all
three scenes is expected: `load` only stages the transition; the scene graph is
instantiated on the first tick.

Each row is a **standalone measurement of one `(scene, config)` pair** — not an additive
term, and not comparable across differently-configured props. Scene memory is
output-coupled, so a figure is valid only for the deployed `aura-device.json` it was
measured against (recorded in the `Harness` column, derived from the config via
`metrics_harness_label`). There is no in-file harness table to hand-edit: to compare a
scene under a different config, deploy a different `aura-device.json` that registers the
scene's clips and wires its scopes — a mismatched or under-configured deploy reproduces the
discredited ~2x headless artifact. Disabling a hardware section (e.g. dropping `audio` or
`ir`) and re-running is the intended way to see that section's heap impact.

| Board | Runtime | Driver | Scene | Harness | `load` Δ (B) | First-tick Δ (B) |
|-------|---------|--------|-------|---------|--------------|-------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | tag | matrix+audio(v4)+motor+ir(tag) | 80 | 15,072 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | red_light_green_light | matrix+audio(v2)+motor+no-ir | 80 | 20,080 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | hardware_test | matrix+audio(v1)+motor+ir(default) | 112 | 13,936 |

The `Harness` column records what each scene was measured against. New rows are formatted
by `metrics_harness_label` from the deployed config as pixel-count/audio-voices/motor/accel/
IR-rx-count parts (e.g. `matrix(117px)+audio(v4)+motor+accel+ir(rx1)`); the motor and accel
parts reflect whether `haptics`/`accelerometer` are declared in the config (#691
config-gates both -- no runtime presence probe). The wire-frame codec (Aura vs. Tag) is a
per-scene choice, not a `DeviceConfig` fact, so it plays no part in the label. The
rows below predate this profiler's config-driven rewrite (#686) and still show the older
hand-maintained `HARNESSES`-table format (matrix scope name, voice count, motor, and IR
codec) — kept as-recorded rather than reformatted, since re-labelling without re-measuring
would misrepresent them as config-derived. These are the in-situ comparison anchors for
future before/after scene-change checks — re-record a scene's row only against the same
deployed config.
