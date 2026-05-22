from __future__ import annotations

__all__ = ["SceneControls"]


class SceneControls:
    """Abstract interface for scene transitions called from within game rules.

    All methods raise ``NotImplementedError`` by default.  ``SceneManager``
    injects itself as the live implementation; standalone callers (e.g. rule
    unit tests) pass the base ``SceneControls()`` instance, which raises on
    any call.

    Transitions are deferred to end-of-tick — the transition is applied after
    ``engine.update(state)`` returns, not immediately inside the rule.
    """

    def load(self, name: str) -> None:
        """Replace the entire scene stack with the named scene."""
        raise NotImplementedError

    def overlay(self, name: str) -> None:
        """Push the named scene on top, suspending the current scene."""
        raise NotImplementedError

    def pop(self) -> None:
        """Unload the top scene and restore the scene below it."""
        raise NotImplementedError
