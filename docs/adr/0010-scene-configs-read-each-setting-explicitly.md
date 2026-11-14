# Scene Configs read each Setting with an explicit line

A Scene Config reads each one-to-one field with its own line in `__init__`, such as `self.max_ammo = settings.get_int(SCENE_NAMESPACE, "max_ammo")`, even though that spells each Setting's name several times: in `scene.json`, in `__slots__`, as the attribute and as the string. Drift between those spellings is caught by one pack-level CPython test, which checks that every declared Setting is read into a field of the same name. It isn't removed by an abstraction in device code.

## Considered Options

- **Typed Setting descriptors** (`max_ammo = IntSetting()` on a `SettingFields` base, naming the Setting through `__set_name__` and caching on first read). Feasible on CircuitPython 10.3.1+ and MicroPython, and type-safe under ADR-0007 without generics. Rejected in the 2026-11 architecture review: it adds layers of abstraction and per-field machinery to microcontroller code to save one line per field.
- **Filling fields reflectively from the declarations** (a `setattr` loop). Rejected: mypy loses every field's type (ADR-0007).
