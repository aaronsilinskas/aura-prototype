# Network transmits are broadcast; identity travels in the payload

A rule sends through **NetworkControls** with `send_ir(data, emitter)` and `send_radio(data)`. Neither takes a recipient. Every prop in range of an IR emitter hears its packet, and `Rfm69RadioTransport` sends with the driver's default destination, the RadioHead broadcast address. When a game needs to say who sent a packet or who it is for, the rule puts a player or entity identity in the payload and the receiving rule decides whether the packet is for it.

The rule dates from #117, which introduced `NetworkControls` and stated it (always broadcast, no recipient parameter, player identity in the payload if needed) without a reason. The likely reasons, to be confirmed: IR is a broadcast medium, so an address could only filter after reception, never choose who receives; one rule for both media keeps rules independent of the transport; and an identity scheme belongs to the game (a Tag player ID, a lobby's entity ID), not to the engine.

## Consequences

- `NetworkEvents.IRReceived` carries no sender. `NetworkEvents.RadioReceived` carries `sender`, the RadioHead from byte as a string, which the engine does not interpret. A game that needs identity on both media reads it from the payload.
- Every prop in range receives every packet, so a rule ignores packets that aren't meant for it. A device's own IR is not one of them: the **IR transmit gate** drops its **Self-echo** before any rule sees it.
