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
