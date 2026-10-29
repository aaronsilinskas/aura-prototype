import re

import pytest

from engine.audio import AudioRegistry

# ---------------------------------------------------------------------------
# AudioRegistry.set_pack_sounds — base population from a ready-made map
# ---------------------------------------------------------------------------


def test_set_pack_sounds_resolves_a_qualified_clip_to_its_given_path() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "packs/effects/basic/sounds/win.wav"})
    registry.set_allowed_packs(frozenset({"basic"}))

    assert registry.path("basic.win") == "packs/effects/basic/sounds/win.wav"


def test_set_pack_sounds_replaces_every_clip_set_before() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "old/win.wav"})
    registry.set_pack_sounds({"basic.lose": "new/lose.wav"})
    registry.set_allowed_packs(frozenset({"basic"}))

    with pytest.raises(ValueError, match=re.escape("basic.win")):
        registry.path("basic.win")


# ---------------------------------------------------------------------------
# AudioRegistry.path — prefix routing
# ---------------------------------------------------------------------------


def test_path_with_scene_prefix_resolves_against_the_active_overlay() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"fire_shot_start": "/sounds/fire_shot_start.wav"})

    assert registry.path("scene.fire_shot_start") == "/sounds/fire_shot_start.wav"


def test_path_with_pack_prefix_resolves_against_the_base() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.game_over": "/sounds/game_over.wav"})
    registry.set_allowed_packs(frozenset({"basic"}))

    assert registry.path("basic.game_over") == "/sounds/game_over.wav"


def test_path_with_scene_prefix_ignores_a_base_entry_of_the_same_stem() -> None:
    """scene. and <pack>. are separate namespaces: a scene can specialise a
    shared clip without the base entry leaking through."""
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})

    with pytest.raises(ValueError, match=re.escape("scene.win")):
        registry.path("scene.win")


# ---------------------------------------------------------------------------
# AudioRegistry.path — raises rather than returning None
# ---------------------------------------------------------------------------


def test_path_with_unprefixed_name_raises_naming_the_reference() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match="missing"):
        registry.path("missing")


def test_path_with_scene_prefix_and_no_active_overlay_raises() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match=re.escape("scene.win")):
        registry.path("scene.win")


def test_path_with_scene_prefix_absent_from_the_active_overlay_raises() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"fire_shot_start": "/sounds/fire_shot_start.wav"})

    with pytest.raises(ValueError, match=re.escape("scene.win")):
        registry.path("scene.win")


def test_path_with_pack_prefix_absent_from_the_base_raises() -> None:
    registry = AudioRegistry()
    registry.set_allowed_packs(frozenset({"basic"}))

    with pytest.raises(ValueError, match=re.escape("basic.win")):
        registry.path("basic.win")


# ---------------------------------------------------------------------------
# AudioRegistry.set_scene_sounds — overlay swap
# ---------------------------------------------------------------------------


def test_set_scene_sounds_none_clears_the_overlay() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"win": "/sounds/win.wav"})

    registry.set_scene_sounds(None)

    with pytest.raises(ValueError):
        registry.path("scene.win")


def test_set_scene_sounds_replaces_the_previous_overlay() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"win": "/sounds/a/win.wav"})

    registry.set_scene_sounds({"win": "/sounds/b/win.wav"})

    assert registry.path("scene.win") == "/sounds/b/win.wav"


# ---------------------------------------------------------------------------
# Pack membership — pack.clip only resolves for packs the active scene
# declared, mirroring EffectResolver's pack.effect membership rule (#814)
# ---------------------------------------------------------------------------


def test_path_raises_when_no_allowed_packs_installed() -> None:
    """A fresh registry's allowed-pack set defaults to None — fail closed."""
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})

    with pytest.raises(ValueError, match="no scene is active"):
        registry.path("basic.win")


def test_path_no_active_scene_error_includes_the_clip_name() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match=re.escape("basic.win")):
        registry.path("basic.win")


def test_path_raises_for_pack_not_declared_by_active_scene() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})
    registry.set_allowed_packs(frozenset({"other"}))

    with pytest.raises(ValueError, match="basic"):
        registry.path("basic.win")


def test_undeclared_pack_error_does_not_say_unknown_sound() -> None:
    """The pack exists in the base — it just isn't declared by the active
    scene — so the message must be honest and distinct from 'Unknown sound'.
    """
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})
    registry.set_allowed_packs(frozenset({"other"}))

    try:
        registry.path("basic.win")
    except ValueError as exc:
        assert "Unknown" not in str(exc)
    else:
        pytest.fail("expected ValueError")


def test_path_membership_checked_before_base_lookup() -> None:
    """A clip absent from the base entirely still fails with the not-declared
    message (not 'Unknown sound') when its pack also isn't in the allowed
    set — membership is checked first.
    """
    registry = AudioRegistry()
    registry.set_allowed_packs(frozenset({"other"}))

    with pytest.raises(ValueError, match="not declared"):
        registry.path("basic.win")


def test_path_succeeds_for_declared_pack() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})
    registry.set_allowed_packs(frozenset({"basic"}))

    assert registry.path("basic.win") == "/sounds/win.wav"


def test_set_allowed_packs_none_clears_pack_prefix_resolution() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})
    registry.set_allowed_packs(frozenset({"basic"}))

    registry.set_allowed_packs(None)

    with pytest.raises(ValueError, match="no scene is active"):
        registry.path("basic.win")


def test_set_allowed_packs_replaces_previous_set() -> None:
    registry = AudioRegistry()
    registry.set_pack_sounds({"basic.win": "/sounds/win.wav"})
    registry.set_allowed_packs(frozenset({"other"}))

    registry.set_allowed_packs(frozenset({"basic"}))

    assert registry.path("basic.win") == "/sounds/win.wav"


def test_scene_prefix_resolution_unaffected_by_missing_allowed_packs() -> None:
    """scene.-prefixed names are scene-local and never gated by allowed packs."""
    registry = AudioRegistry()
    registry.set_scene_sounds({"win": "/sounds/win.wav"})
    # No set_allowed_packs call at all — pack.* would fail closed, but scene.* must not.

    assert registry.path("scene.win") == "/sounds/win.wav"
