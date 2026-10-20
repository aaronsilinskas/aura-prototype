# Mocking in Kotlin

> Placeholder: this file was seeded from general MockK knowledge, not yet
> from real project experience. Tighten it up with actual gotchas as they
> come up on Kotlin projects.

## Relaxed mocks hide missing stubs

`mockk<T>(relaxed = true)` returns default values (0, "", empty collections,
nulls) for any unstubbed call instead of failing. A test can pass because a
dependency silently returned a default, not because the behavior under test
is actually correct. Prefer strict mocks and stub only what the test needs,
so an unstubbed call fails loudly instead of returning a silent zero.

```kotlin
// Risky: relaxed mock returns 0 for unstubbed getTotal(), test can pass for the wrong reason
val cart = mockk<Cart>(relaxed = true)

// Safer: strict mock forces every used call to be stubbed explicitly
val cart = mockk<Cart>()
every { cart.getTotal() } returns 15
```

## Dependency injection

```kotlin
// Easy to mock
fun processPayment(order: Order, paymentClient: PaymentClient): Receipt =
    paymentClient.charge(order.total)

// Hard to mock
fun processPayment(order: Order): Receipt {
    val client = StripeClient(System.getenv("STRIPE_KEY"))
    return client.charge(order.total)
}
```

## SDK-style interfaces

Prefer one method per external operation over one generic call with
conditional branching:

```kotlin
interface Api {
    fun getUser(id: String): User
    fun getOrders(userId: String): List<Order>
    fun createOrder(data: OrderData): Order
}
```

Each method is independently mockable (`every { api.getUser(any()) } returns
...`), with one clear shape returned per call.
