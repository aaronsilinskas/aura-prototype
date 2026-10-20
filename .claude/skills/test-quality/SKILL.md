---
name: test-quality
description: "Review and audit tests against a quality bar: names that state the guaranteed behavior, one behavior per test, and coverage traced to product guarantees. Use when reviewing or auditing a test or a whole suite, naming test functions, planning what a feature's tests should cover, asking whether a test is any good, or running the tests pass of a review. The loop that produces tests belongs to tdd."
argument-hint: "test file, suite, or feature to review"
---

# Test Quality

The quality bar for tests. Run it as its own pass over existing tests, or over a coverage plan before the tests exist. The bar is the same whoever wrote the tests.

This skill does not cover the loop. Process, seams, vertical slices and the test anti-patterns (implementation-coupled, tautological) live in the `tdd` skill, and this bar assumes them. A test that fails `tdd`'s anti-patterns fails this bar too.

Two neighbouring passes have their own skills: implementation code is `code-quality`, comments and docstrings are `comments`.

Read the project's `GLOSSARY.md` (if it exists) so test names use the project's domain language.

Ask of every test: **"What user-visible or system-level guarantee does this verify?"**

## Test naming

Test names are the primary communication surface. They should read like a statement of guaranteed behavior.

**Format:** `test_<subject>_<condition_or_scenario>` or `test_<what_is_guaranteed>`

**Goal:** a failing test's name alone should tell you what broke, not just which line.

### Good names

```python
# Explains the guarantee and why it matters
def test_palette_wraps_position_so_out_of_range_values_still_render():
def test_effect_value_clamps_to_zero_when_level_is_below_threshold():
def test_renderer_produces_consistent_color_for_same_position():
def test_timer_accumulates_delta_across_multiple_updates():
def test_fire_step_produces_higher_intensity_at_base():
```

### Bad names

```python
# Mirrors code structure, doesn't say what's guaranteed
def test_get_value():
def test_palette_lut():
def test_update_returns_none():
def test_effect_calls_step():

# Over-specific to implementation details
def test_list_index_0_is_255():
def test_loop_iterates_16_times():
```

### Name anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| `test_<method_name>` | Tests the implementation, not behavior | Name the behavior the method enables |
| `test_<class>_works` | Vacuous: everything "works" until it doesn't | State exactly what works and under what condition |
| `test_<thing>_returns_<type>` | A type check, not a behavior check | Test the value contract, not the type |
| `test_<step>_step` | Just echoes code structure | Describe what the step produces |

### The name must match what the test actually does

A name that overstates the test lies about coverage. Check the name against the inputs fired and the assertions made. They must agree.

```python
# Name claims "near zero", but fires exactly zero
def test_near_zero_axis_yields_near_zero_progress():
    fire(x=0.0)

# Fix: rename to the boundary it actually guards
def test_zero_acceleration_yields_zero_progress():
    fire(x=0.0)
```

If the name says "X causes Y", the test must change X and observe Y.

### A named test beats an explanatory comment

Behavior complex enough that someone wants to narrate it in a comment or docstring belongs in a named test that asserts it. The test documents the contract, proves it holds, and fails when it regresses. Treat each "this handles ..." comment in source as a missing test: name it and assert it (e.g. `test_<thing>_when_<condition>_...`).

## Test structure

### One behavior per test

Each test verifies exactly one behavioral guarantee. If a test has several unrelated assertions, split it.

```python
# Too broad: two unrelated guarantees
def test_renderer():
    ...
    assert color == 0xFF0000
    assert "demo" in renderer.name

# Better: focused guarantees
def test_renderer_produces_packed_color_for_valid_input():
    ...
    assert color == 0xFF0000

def test_renderer_exposes_effect_name():
    ...
    assert renderer.name == "demo"
```

### Arrange / Act / Assert

Use a clear three-section layout with a blank line between each section. Don't add comments labelling the sections. The structure should be evident.

```python
def test_timer_accumulates_delta_across_multiple_updates():
    timer = EffectTimer()

    timer.update(0.1)
    timer.update(0.05)

    assert timer.elapsed == pytest.approx(0.15)
```

### Assert through the public interface

Internal state is only worth asserting when the product relies on it being observable (e.g. state shared between update and render). Anything else that reaches past the interface is `tdd`'s implementation-coupled anti-pattern.

## Planning coverage

Coverage traces back to product guarantees, not code paths. Code that no behavioral test covers is a candidate for removal or refactoring, not for a test that just executes it.

### Coverage checklist for any feature

- [ ] **Happy path:** does it produce the correct result for normal inputs?
- [ ] **Boundary values:** what happens at zero, max, min, empty?
- [ ] **Invalid or unexpected inputs:** does it fail safely or clamp gracefully?
- [ ] **Idempotence:** calling it twice, same result? Or does state accumulate correctly?
- [ ] **Isolation:** does it behave correctly in isolation, with no hidden dependency on ordering?
- [ ] **Reset / restart behavior:** does re-initialization give a clean slate?

### Product-focused edge cases

Ask: *what behavior would a user (or caller) actually notice if broken?*

- Output range violations (e.g. a color channel above 255, a position out of bounds)
- State corruption after repeated calls
- Delta-time edge cases (zero delta, a very large spike)
- Empty or degenerate inputs (empty palette, zero-length strip)
- Two features used together (e.g. scale and sparkle applied to the same effect)

Don't manufacture edge cases that can't occur in a real call sequence.

## What to avoid

- **Tests that just exercise a code path.** If deleting the test would have zero impact on catching real bugs, it doesn't need to exist.
- **Asserting the return type when the value itself can be asserted.** `assert color == 0xFF0000` is more useful than `assert isinstance(color, int)`.
- **Testing framework or library behavior.** The standard library's own correctness is not your job to verify.
- **Tests built purely for line coverage.** Coverage is a byproduct of good behavioral tests, not a goal in itself.

## Examples

### Reviewing an existing test

Given:

```python
def test_effect_renderer_returns_rgb_int() -> None:
    ...
    assert isinstance(color, int)
    assert color == 0xFF0000
```

Issues:

- The name says `returns_rgb_int`, but the type check is noise once the value is asserted.
- Two assertions, and the first is redundant.
- The name doesn't explain *why* 0xFF0000. What palette and position were expected to produce red?

Improved:

```python
def test_renderer_returns_full_red_at_max_value_with_two_stop_palette():
    effect = Effect("demo", lambda _: 1.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))  # black → red gradient
    renderer = EffectRenderer(effect, palette)
    ...
    assert color == 0xFF0000
```

### Planning the tests for a module or feature

1. Read the public API and identify the behavioral guarantees it makes.
2. List the happy-path cases, boundary values and real-world edge cases separately.
3. Plan one test per guarantee, each with a descriptive name.
4. Each test asserts only what its name claims. No bonus assertions.

## Mocking

The rule (mock at system boundaries only, never your own modules) lives in `tdd`. What this skill adds is the per-language mechanics, which trip people up even when the rule is followed. Load only the file for the language under review:

- Python: [mocking-python.md](mocking-python.md)
- TypeScript: [mocking-typescript.md](mocking-typescript.md)
- Kotlin: [mocking-kotlin.md](mocking-kotlin.md)

### Designing for mockability

A test that is hard to mock usually points at the source, not the test. At a system boundary, the source should:

1. **Take external dependencies in** (dependency injection) rather than constructing them internally.
2. **Expose one function or method per external operation** rather than one generic call with conditional branching, so each mock returns exactly one shape and the test setup shows which endpoints a test exercises.

Fixing the source is a `code-quality` matter: report it there rather than working around it in the test.

## Checklist

- [ ] Each test name states a guarantee, and matches the inputs fired and the assertions made
- [ ] One behavior per test, laid out as Arrange / Act / Assert without section comments
- [ ] Assertions go through the public interface, with expected values from an independent source (see `tdd`'s anti-patterns)
- [ ] Coverage traces to product guarantees: happy path, boundaries, invalid input, idempotence, isolation, reset
- [ ] No test exists only to execute a code path, check a type, or test a library
- [ ] Mocks sit at system boundaries, and the matching language guide's gotchas are avoided
