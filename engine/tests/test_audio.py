from engine.audio import AudioRegistry


def test_register_and_retrieve_a_clip():
    registry = AudioRegistry()

    registry.register("fire_ambient", "/sounds/fire.wav")

    assert registry.path("fire_ambient") == "/sounds/fire.wav"


def test_returns_none_for_unregistered_name():
    registry = AudioRegistry()

    assert registry.path("missing") is None


def test_registering_same_name_twice_overwrites_previous_entry():
    registry = AudioRegistry()
    registry.register("hit", "/sounds/hit_v1.wav")

    registry.register("hit", "/sounds/hit_v2.wav")

    assert registry.path("hit") == "/sounds/hit_v2.wav"
