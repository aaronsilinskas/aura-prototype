# IR reception carries no direction

`NetworkEvents.IRReceived` tells a rule what arrived (the payload, its **IR signal strength** and **IR error margin**) but not which receiver heard it or from which side. An **IR multi-receiver** puts each receiver on its own data line and returns the packet with the lowest error margin. That pick improves reception only. It is not a direction finder, and rules never see which receiver won (#1264): `InfraredTransceiver` and the **Simulated device** keep the pick as hardware and test telemetry.

`IRReceived` used to have a `best_receiver` field that the scene tick always filled with `None`, and no rule read it. #1264 dropped it rather than wire it through, so the event no longer promises data it doesn't carry. Its triage gave two reasons: the multi-receiver was already defined as a reliability aid with no hit direction, and receivers have no rule-facing names (the one `ir.receive` **Capability** covers any IR receiver), so there is no identity a rule could use. The reason the multi-receiver was never meant to give direction, to be confirmed: bench tests of TSOP-series receiver arrays found no reliable link between hit direction and which receiver decoded best. Wall reflections reach every receiver, and only heavily shrouded side receivers gave any sense of direction.

## Considered Options

- **Pass the winning receiver's identity to rules.** Rejected: it needs a decision on what identity a rule gets (the transceiver knows a `PulseReader`, the Simulated device an index), and a rule would read it as a direction it doesn't reliably give.
- **Drop the field; the pick stays hardware telemetry (chosen).** The event carries only what reception can vouch for, and the pick is still there for hardware tests and the Simulated device.

## Consequences

- A multi-receiver is selected by listing two or more `rx` pins. More receivers mean better reception, never a direction.
- A game that wants hit direction has to carry it some other way, such as in the shot's payload. It can't come from which receiver heard the shot.
