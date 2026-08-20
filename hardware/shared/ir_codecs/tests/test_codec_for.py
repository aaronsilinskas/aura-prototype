"""Behaviour-driven tests for convention-based IR codec resolution."""

import builtins

import pytest

from hardware.shared.ir_codecs import UnknownCodecError, codec_for
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder


def test_codec_for_aura_returns_the_aura_encoder_and_decoder_pair():
    assert codec_for("aura") == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_codec_for_tag_returns_the_tag_encoder_and_decoder_pair():
    assert codec_for("tag") == (TagInfraredEncoder, TagInfraredDecoder)


def test_codec_for_with_no_name_defaults_to_aura():
    assert codec_for() == (AuraInfraredEncoder, AuraInfraredDecoder)


def test_codec_for_unknown_name_raises_unknown_codec_error_by_type():
    with pytest.raises(UnknownCodecError):
        codec_for("tv_remote")


def test_unknown_codec_error_names_the_known_codecs():
    with pytest.raises(UnknownCodecError) as exc_info:
        codec_for("tv_remote")

    assert exc_info.value.available == ["aura", "tag"]
    assert "aura" in str(exc_info.value)
    assert "tag" in str(exc_info.value)


def test_codec_for_unknown_name_is_still_catchable_as_a_value_error():
    # UnknownCodecError is a bespoke ValueError subclass (hardware may not
    # import engine.packs, where the analogous UnknownItemError lives), so a
    # caller that only catches ValueError still catches this.
    with pytest.raises(ValueError):
        codec_for("tv_remote")


def test_codec_for_broken_existing_module_propagates_its_own_import_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "hardware.shared.ir_codecs.aura":
            raise ModuleNotFoundError(
                "no module named 'missing_dependency'", name="missing_dependency"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ModuleNotFoundError, match="missing_dependency"):
        codec_for("aura")
