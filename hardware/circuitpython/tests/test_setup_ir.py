"""Tests for _setup_ir in device_builder — builds IR hardware objects and returns
the transmitter map + single receiver for injection into HardwareNetworkControls.

Assembly only: writer *selection* (the ``rp2pio`` import-probe inside
``_make_writer``) is exercised separately in ``test_setup_ir_pio.py``. These
tests inject a trivial fake ``writer_factory`` so assembly is CPython-testable
without stubbing ``rp2pio``/``pulseio`` for the writer path.

Covers:
- _setup_ir defaults writer_factory to _make_writer
- _setup_ir calls writer_factory once per wired emitter, with that emitter's pin
- _setup_ir with a line_pin returns a LINE transmitter and receiver
- _setup_ir with cone_pin returns LINE and CONE transmitters
- _setup_ir with aoe_pin returns LINE and AREA_OF_EFFECT transmitters
- _setup_ir with all pins returns all three transmitters
- _setup_ir omits any emitter (line/cone/area_of_effect) when its pin is None
- _setup_ir wires every transmitter and the receiver to the same gate
- _setup_ir receiver is wired to rx_pin
- _setup_ir defaults to Aura codecs when encoder/decoder are omitted
- _setup_ir wires a provided encoder/decoder pair into transmitters/receiver
- _setup_ir reuses the same encoder instance across all wired transmitters
"""

from __future__ import annotations

import inspect
import sys
import types

# ---------------------------------------------------------------------------
# Stub out CircuitPython-only hardware modules before importing device_builder.
# We must be careful to set up all modules that device_builder.py imports at
# module level, including a minimal pulseio (only PulseIn is touched by
# assembly — the receiver's PulseIn wiring — since the injected fake
# writer_factory never calls the real PulseOut-backed writer path).
# ---------------------------------------------------------------------------

for _name in (
    "adafruit_is31fl3741",
    "adafruit_is31fl3741.adafruit_rgbmatrixqt",
    "board",
    "busio",
    "digitalio",
    "pulseio",
):
    sys.modules.setdefault(_name, types.ModuleType(_name))

# adafruit_is31fl3741 constants
_is31 = sys.modules["adafruit_is31fl3741"]
if not hasattr(_is31, "MUST_BUFFER"):
    _is31.MUST_BUFFER = 0  # type: ignore[attr-defined]

# adafruit_rgbmatrixqt stub
_rgbqt = sys.modules["adafruit_is31fl3741.adafruit_rgbmatrixqt"]
if not hasattr(_rgbqt, "Adafruit_RGBMatrixQT"):
    _rgbqt.Adafruit_RGBMatrixQT = type("Adafruit_RGBMatrixQT", (), {})  # type: ignore[attr-defined]

# board pin stubs
_board = sys.modules["board"]
for _attr in ("SCL", "SDA", "EXTERNAL_POWER", "D9", "D10"):
    if not hasattr(_board, _attr):
        setattr(_board, _attr, object())

# digitalio stubs
_digitalio = sys.modules["digitalio"]
if not hasattr(_digitalio, "DigitalInOut"):
    _digitalio.DigitalInOut = type(  # type: ignore[attr-defined]
        "DigitalInOut",
        (),
        {
            "__init__": lambda self, pin: None,
            "switch_to_input": lambda self, **kw: None,
            "switch_to_output": lambda self, **kw: None,
            "value": True,
        },
    )
if not hasattr(_digitalio, "Pull"):
    _pull = types.SimpleNamespace(UP=0, DOWN=1)
    _digitalio.Pull = _pull  # type: ignore[attr-defined]

# busio stubs
_busio = sys.modules["busio"]
if not hasattr(_busio, "I2C"):
    _busio.I2C = type("I2C", (), {"__init__": lambda self, *a: None})  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# pulseio.PulseIn stub — the receiver's rx-side wiring, untouched by writer
# selection. No PulseOut stub is needed: the injected fake writer_factory
# never calls _make_writer, so pulseio.PulseOut is never constructed here.
# ---------------------------------------------------------------------------


class _FakePulseIn:
    """Stub for pulseio.PulseIn."""

    def __init__(self, pin, *, maxlen=256, idle_state=True) -> None:
        self.pin = pin
        self.maxlen = maxlen
        self.idle_state = idle_state
        self._data: list[int] = []

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, index: int) -> int:
        return self._data[index]

    def __delitem__(self, index: int) -> None:
        del self._data[index]

    def clear(self) -> None:
        self._data.clear()


_pulseio = sys.modules["pulseio"]
_pulseio.PulseIn = _FakePulseIn  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Now import what we're testing
# ---------------------------------------------------------------------------


from engine.network import AREA_OF_EFFECT, CONE, LINE  # noqa: E402
from hardware.circuitpython.device_builder import _make_writer, _setup_ir  # noqa: E402
from hardware.shared.ir_protocol import AuraInfraredDecoder, AuraInfraredEncoder  # noqa: E402
from hardware.shared.tag_protocol import TagInfraredDecoder, TagInfraredEncoder  # noqa: E402

_RX_PIN = object()
_LINE_PIN = object()
_CONE_PIN = object()
_AOE_PIN = object()


class _FakeWriter:
    """Trivial stand-in PulseWriter recording the pin it was built for."""

    def __init__(self, pin) -> None:
        self.pin = pin


_FAKE_WRITER_KIND = "fake"


def _fake_writer_factory(pin):
    return _FakeWriter(pin), _FAKE_WRITER_KIND


# ---------------------------------------------------------------------------
# _setup_ir — writer_factory seam
# ---------------------------------------------------------------------------


def test_setup_ir_writer_factory_defaults_to_make_writer():
    """The writer_factory parameter defaults to _make_writer."""
    assert inspect.signature(_setup_ir).parameters["writer_factory"].default is _make_writer


def test_setup_ir_calls_writer_factory_once_per_wired_emitter_with_its_own_pin():
    """writer_factory(pin) is invoked once per wired emitter, each with its own pin,
    in IR_EMITTERS order regardless of the emitter_pins mapping's own key order."""
    calls: list[object] = []

    def recording_factory(pin):
        calls.append(pin)
        return _FakeWriter(pin), _FAKE_WRITER_KIND

    _setup_ir(
        [_RX_PIN],
        {AREA_OF_EFFECT: _AOE_PIN, CONE: _CONE_PIN, LINE: _LINE_PIN},
        writer_factory=recording_factory,
    )
    assert calls == [_LINE_PIN, _CONE_PIN, _AOE_PIN]


def test_setup_ir_uses_writer_returned_by_writer_factory():
    """Each transmitter's writer is exactly what writer_factory returned for its pin."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert transmitters[LINE]._writer.pin is _LINE_PIN


def test_setup_ir_returns_writer_kind_reported_by_writer_factory():
    """The returned writer_kind is exactly what writer_factory reported, not
    re-derived from the writer instance -- #763's hand-off so build_hardware's
    ir narration can ask rather than re-probe rp2pio."""
    _transmitters, _receiver, writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert writer_kind == _FAKE_WRITER_KIND


def test_setup_ir_returns_none_writer_kind_when_no_emitters_wired():
    """An rx-only ir config (no emitters) never calls writer_factory, so there
    is no writer kind to report."""
    _transmitters, _receiver, writer_kind = _setup_ir(
        [_RX_PIN], {}, writer_factory=_fake_writer_factory
    )
    assert writer_kind is None


# ---------------------------------------------------------------------------
# _setup_ir — transmitter map
# ---------------------------------------------------------------------------


def test_setup_ir_includes_line_transmitter_when_line_in_emitter_pins():
    """_setup_ir wires the LINE emitter when its pin is in emitter_pins."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert LINE in transmitters


def test_setup_ir_omits_cone_when_cone_is_absent_from_emitter_pins():
    """No CONE entry in transmitter map when cone is absent from emitter_pins."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert CONE not in transmitters


def test_setup_ir_omits_aoe_when_aoe_is_absent_from_emitter_pins():
    """No AREA_OF_EFFECT entry when it is absent from emitter_pins."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert AREA_OF_EFFECT not in transmitters


def test_setup_ir_includes_cone_transmitter_when_cone_in_emitter_pins():
    """CONE transmitter is present when cone is in emitter_pins."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN, CONE: _CONE_PIN}, writer_factory=_fake_writer_factory
    )
    assert CONE in transmitters


def test_setup_ir_includes_aoe_transmitter_when_aoe_in_emitter_pins():
    """AREA_OF_EFFECT transmitter is present when it is in emitter_pins."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN, AREA_OF_EFFECT: _AOE_PIN}, writer_factory=_fake_writer_factory
    )
    assert AREA_OF_EFFECT in transmitters


def test_setup_ir_all_pins_returns_three_transmitters():
    """All three emitter keys are present when all three are in emitter_pins."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN],
        {LINE: _LINE_PIN, CONE: _CONE_PIN, AREA_OF_EFFECT: _AOE_PIN},
        writer_factory=_fake_writer_factory,
    )
    assert set(transmitters.keys()) == {LINE, CONE, AREA_OF_EFFECT}


def test_setup_ir_transmitters_share_the_gate_with_receiver():
    """The shared IrTransmitGate is injected into the receiver and every transmitter."""
    transmitters, receiver, _writer_kind = _setup_ir(
        [_RX_PIN],
        {LINE: _LINE_PIN, CONE: _CONE_PIN, AREA_OF_EFFECT: _AOE_PIN},
        writer_factory=_fake_writer_factory,
    )
    gate = receiver._gate
    assert gate is not None
    for emitter in (LINE, CONE, AREA_OF_EFFECT):
        assert transmitters[emitter]._gate is gate


# ---------------------------------------------------------------------------
# _setup_ir — receiver
# ---------------------------------------------------------------------------


def test_setup_ir_receiver_is_wired_to_rx_pin():
    """The returned receiver reads pulses from the rx_pin PulseIn buffer."""
    _transmitters, receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    pulsein = receiver._reader._pulsein
    assert pulsein.pin is _RX_PIN


def test_setup_ir_receiver_pulsein_uses_active_low_idle_state():
    """PulseIn is constructed with idle_state=True for active-low IR receivers."""
    _transmitters, receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    pulsein = receiver._reader._pulsein
    assert pulsein.idle_state is True


def test_setup_ir_omits_line_when_line_pin_is_none():
    """No LINE entry in transmitter map when emitter_pins is empty — LINE is
    optional, like cone/area_of_effect."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {}, writer_factory=_fake_writer_factory
    )
    assert LINE not in transmitters


# ---------------------------------------------------------------------------
# _setup_ir — codec injection
# ---------------------------------------------------------------------------


def test_setup_ir_defaults_to_aura_encoder_for_transmitters():
    """Omitting encoder wires transmitters with AuraInfraredEncoder."""
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert isinstance(transmitters[LINE]._encoder, AuraInfraredEncoder)


def test_setup_ir_defaults_to_aura_decoder_for_receiver():
    """Omitting decoder wires the receiver with AuraInfraredDecoder."""
    _transmitters, receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, writer_factory=_fake_writer_factory
    )
    assert isinstance(receiver._decoder, AuraInfraredDecoder)


def test_setup_ir_wires_provided_encoder_into_transmitters():
    """A passed-in encoder is used by the wired transmitters."""
    encoder = TagInfraredEncoder()
    transmitters, _receiver, _writer_kind = _setup_ir(
        [_RX_PIN],
        {LINE: _LINE_PIN, CONE: _CONE_PIN, AREA_OF_EFFECT: _AOE_PIN},
        encoder=encoder,
        writer_factory=_fake_writer_factory,
    )
    assert transmitters[LINE]._encoder is encoder
    assert transmitters[CONE]._encoder is encoder
    assert transmitters[AREA_OF_EFFECT]._encoder is encoder


def test_setup_ir_wires_provided_decoder_into_receiver():
    """A passed-in decoder is used by the receiver."""
    decoder = TagInfraredDecoder()
    _transmitters, receiver, _writer_kind = _setup_ir(
        [_RX_PIN], {LINE: _LINE_PIN}, decoder=decoder, writer_factory=_fake_writer_factory
    )
    assert receiver._decoder is decoder
