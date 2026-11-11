# Mocking in Python

## Patch where it's looked up, not where it's defined

`unittest.mock.patch` (and `pytest-mock`'s `mocker.patch`) replace a name in
the *importing* module's namespace, not in the module where the name was
originally defined. Patching the definition site silently does nothing if the
caller imported the name directly.

```python
# payments.py
from stripe_client import StripeClient

def process_payment(order):
    client = StripeClient()
    return client.charge(order.total)
```

```python
# WRONG: patches stripe_client.StripeClient, but payments.py already
# holds its own reference via `from stripe_client import StripeClient`
mocker.patch("stripe_client.StripeClient")

# RIGHT: patch the name where it's used
mocker.patch("payments.StripeClient")
```

## Dependency injection

```python
# Easy to mock
def process_payment(order, payment_client):
    return payment_client.charge(order.total)

# Hard to mock
def process_payment(order):
    client = StripeClient(os.environ["STRIPE_KEY"])
    return client.charge(order.total)
```

## SDK-style interfaces

Prefer one method per external operation over one generic call with
conditional branching. Python doesn't have JS's object-of-arrow-functions
idiom for this. It's usually a class or a small module of named functions:

```python
class Api:
    def get_user(self, id): ...
    def get_orders(self, user_id): ...
    def create_order(self, data): ...
```

Each method is independently mockable via `mocker.patch.object(api,
"get_user")`, with no conditional logic in the mock and exactly one shape
returned per call.

## Typing fakes

mypy checks test bodies and every call they make into production code, so a
fake handed to production must type-check as the real thing. Each kind of fake
has one pattern:

- **A fake of a project-owned class subclasses the real base.** Override only
  what the test needs. When the base's signature changes, mypy flags the fake.
  Don't add a `cast`, or a production `Protocol` for the test's sake.
- **A fake of a CircuitPython or third-party type gets one typed cast helper**,
  written beside the fake. The helper is the only place the fake is passed off
  as the real type, and call sites use the helper. CircuitPython modules exist
  only as stubs, so for them the cast names the type as a string:

  ```python
  def fake_pulse_in(pulses: list[int] | None = None, maxlen: int = 256) -> "pulseio.PulseIn":
      return cast("pulseio.PulseIn", FakePulseIn(pulses, maxlen))
  ```

  When the test also asserts on the fake's own state, keep a fake-typed name
  and cast only at the handoff: `UsbCdcTransport(as_serial(serial))`, then
  `assert serial.written == ...`. mypy doesn't check that the fake matches the
  real type's shape, so a missing method fails the test at runtime instead.
- **Narrow union and Optional values with `assert`**: `assert x is not None`
  or `assert isinstance(x, T)`, not `cast` or `# type: ignore`. A wrong variant
  then fails with a clear assertion instead of an `AttributeError`.

Tests run on CPython only, so they import `cast` and `TYPE_CHECKING` from
`typing` directly rather than using the device's bare `TYPE_CHECKING = False`.
