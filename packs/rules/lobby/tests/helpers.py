"""Test helpers for the lobby rule pack.

``RecordingSceneControls`` mirrors ``engine.tests.helpers.RecordingSceneReboot``
(the reboot fake from issue #910) but on the rule-facing ``SceneControls``
face, since ``LobbySelectRule`` reaches ``state.scene_controls.reboot_into``
directly -- rule unit tests never go through a live ``SceneManager``.
"""

from __future__ import annotations

from engine.state import SceneControls


class RecordingSceneControls(SceneControls):
    """Test recorder for ``SceneControls.reboot_into``, called directly by a rule.

    Only ``reboot_into`` is overridden; every other method still raises
    ``NotImplementedError`` from the base class, since ``LobbySelectRule``
    never calls them.
    """

    def __init__(self) -> None:
        self.reboot_into_calls: list[str] = []

    def reboot_into(self, target: str) -> None:
        self.reboot_into_calls.append(target)
