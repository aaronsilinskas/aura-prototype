# Mocking in Python: aura rules

aura's additions to the `test-quality` skill's `mocking-python.md` reference. Apply both; where they differ, this file wins.

## Typing fakes

mypy checks test bodies and every call they make into production code, so a fake handed to production must type-check as the real thing. Each kind of fake has one pattern:

- **A fake of a project-owned class subclasses the real base.** Override only what the test needs. When the base's signature changes, mypy flags the fake. Don't add a `cast`, or a production `Protocol` for the test's sake.
- **A fake of a CircuitPython or third-party type gets one typed cast helper**, written beside the fake. The helper is the only place the fake is passed off as the real type, and call sites use the helper. CircuitPython modules exist only as stubs, so for them the cast names the type as a string:

  ```python
  def fake_pulse_in(pulses: list[int] | None = None, maxlen: int = 256) -> "pulseio.PulseIn":
      return cast("pulseio.PulseIn", FakePulseIn(pulses, maxlen))
  ```

  When the test also asserts on the fake's own state, keep a fake-typed name and cast only at the handoff: `UsbCdcTransport(as_serial(serial))`, then `assert serial.written == ...`. mypy doesn't check that the fake matches the real type's shape, so a missing method fails the test at runtime instead.
- **Narrow union and Optional values with `assert`**: `assert x is not None` or `assert isinstance(x, T)`, not `cast` or `# type: ignore`. A wrong variant then fails with a clear assertion instead of an `AttributeError`.

Tests run on CPython only, so they import `cast` and `TYPE_CHECKING` from `typing` directly rather than using the device's bare `TYPE_CHECKING = False`.
