# Mocking in TypeScript

## `jest.mock` factories are hoisted

`jest.mock(...)` calls are hoisted above imports by Babel/ts-jest, before any
local variables are initialized. Referencing a plain local variable inside
the factory throws `ReferenceError: Cannot access '...' before
initialization`. Jest only exempts variable names prefixed with `mock`.
Reach for `jest.doMock` (not hoisted) if you need a factory that closes over
an arbitrary local.

```typescript
// WRONG: hoisting means `client` doesn't exist yet when the factory runs
const client = { charge: jest.fn() };
jest.mock("./stripe-client", () => ({ StripeClient: () => client }));

// RIGHT: name must start with `mock` to survive hoisting
const mockClient = { charge: jest.fn() };
jest.mock("./stripe-client", () => ({ StripeClient: () => mockClient }));
```

## Dependency injection

```typescript
// Easy to mock
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to mock
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

## SDK-style interfaces

Create one function per external operation instead of a single generic
fetcher with conditional logic:

```typescript
// GOOD: each function is independently mockable
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: mocking requires conditional logic inside the mock
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

The SDK approach means each mock returns one specific shape, there's no
conditional logic in test setup, it's easy to see which endpoints a test
exercises, and each endpoint keeps its own type safety.
