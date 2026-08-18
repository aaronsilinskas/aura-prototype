"""Behaviour-driven tests for convention-based IR codec resolution.

Covers:
- codec_for() resolving "aura" and "tag" to their class pairs
- codec_for()'s default name ("aura") always resolving
- UnknownCodecError raised (by type) for a name with no matching module
- UnknownCodecError naming the known codecs
"""

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
