"""The probe: a card scene whose one rule records every event it hears.

The ``probe`` fixture in ``app/tests/conftest.py`` hands out a :class:`Probe`.
The probe scene's rule imports this module by its stable path and calls
:func:`record`, so renaming a test file can't break the scene's import.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from app.scene_composition import SceneBoot, build_scene_boot
from engine.events import Event
from engine.log import Logger
from engine.pack_catalog import SettingOverrides
from engine.state import GameState
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage

_E = TypeVar("_E", bound=Event)

PROBE_SCENE = "probe"
"""The probe scene's name, which the default boot mapping names as ``default_scene``."""

HEARD: list[tuple[Event, GameState]] = []
"""Every ``(event, state)`` pair the probe's rule handled, oldest first."""

_RULE_SOURCE = """\
from app.tests.probe import record
from engine.engine import GameRule


class _ProbeRule(GameRule):
    def handle_event(self, event, state):
        record(event, state)


RULE = _ProbeRule()
"""


def record(event: Event, state: GameState) -> None:
    """Record that the probe's rule handled *event* while the scene's state was *state*."""
    HEARD.append((event, state))


def no_reset() -> None:
    """A reset that fails the test: pass it where a boot must not reset the device."""
    raise AssertionError("the boot reset the device")


class Probe:
    """Writes the probe scene onto a card and boots it, then reports what its rule heard."""

    def __init__(self, storage: DeviceStorage) -> None:
        self.storage = storage
        """The card the probe scene is written to; give it to the booted hardware."""

    def boot(
        self,
        hw: DeviceHardware,
        *,
        scene_json: dict[str, object] | None = None,
        boot_mapping: dict | None = None,
        reset: Callable[[], None] = no_reset,
        timer: Timer | None = None,
        logger: Logger | None = None,
        setting_overrides: SettingOverrides | None = None,
    ) -> SceneBoot:
        """Write the probe scene onto :attr:`storage` and boot *hw* through ``build_scene_boot``.

        *hw* must carry :attr:`storage` as its storage, or the boot can't find
        the scene. *scene_json* adds keys to the scene's ``scene.json``
        (``requires``, ``ir_codec``, ``settings``, ...) over a minimal manifest.
        *boot_mapping* defaults to one naming the probe as ``default_scene``.
        The rest pass straight to ``build_scene_boot``; by default a reset
        fails the test.
        """
        self._write_scene(scene_json or {})
        return build_scene_boot(
            hw,
            boot_mapping if boot_mapping is not None else {"default_scene": PROBE_SCENE},
            reset=reset,
            timer=timer,
            logger=logger,
            setting_overrides=setting_overrides,
        )

    def heard(self, event_type: type[_E]) -> list[tuple[_E, GameState]]:
        """Return the ``(event, state)`` pairs the rule handled whose event is an *event_type*.

        ``heard(Event)`` is everything it handled, oldest first.
        """
        return [(event, state) for event, state in HEARD if isinstance(event, event_type)]

    def state(self) -> GameState:
        """Return the ``GameState`` the rule saw when it handled its first event.

        Fails the test when the rule has handled nothing yet; tick the boot first.
        """
        assert HEARD, "the probe's rule has handled no event; tick the boot first"
        return HEARD[0][1]

    def events(self, event_type: type[_E]) -> list[_E]:
        """Return the events of *event_type* the rule handled, oldest first."""
        return [event for event, _ in self.heard(event_type)]

    def _write_scene(self, extra: dict[str, object]) -> None:
        aura_packs = Path(self.storage.path("aura_packs"))
        scene_dir = aura_packs / "scenes" / PROBE_SCENE
        rules_dir = scene_dir / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        for package in (aura_packs, aura_packs / "scenes", scene_dir, rules_dir):
            (package / "__init__.py").touch()
        manifest: dict[str, object] = {"version": "1.0", "effect_packs": [], "rule_packs": []}
        manifest.update(extra)
        (scene_dir / "scene.json").write_text(json.dumps(manifest))
        (rules_dir / "probe_rule.py").write_text(_RULE_SOURCE)
