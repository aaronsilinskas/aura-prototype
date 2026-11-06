"""Settings — the resolved, read-only start-up values a scene and its packs declare."""

from __future__ import annotations

__all__ = [
    "SettingDeclaration",
    "SettingValueError",
    "Settings",
    "UnknownSettingError",
    "parse_declarations",
    "resolve_settings",
]


class UnknownSettingError(LookupError):
    """No Setting *name* is declared in *namespace* for this scene."""

    def __init__(self, namespace: str, name: str) -> None:
        self.namespace = namespace
        self.name = name
        super().__init__(f"No Setting '{name}' is declared in namespace '{namespace}'")


class Settings:
    """One scene's resolved Settings, read by namespace and name.

    The namespace is ``scene`` for the scene's own Settings, or a pack's
    folder name for that pack's. Built once by the ``PackCatalog`` scan; there
    is no write path.
    """

    __slots__ = ("_values",)

    def __init__(self, values: dict[str, dict[str, object]] | None = None) -> None:
        self._values = {namespace: dict(names) for namespace, names in (values or {}).items()}

    def get(self, namespace: str, name: str) -> object:
        """Return Setting *name* of *namespace*.

        Raises:
            UnknownSettingError: *namespace* declares no Setting *name*.
        """
        names = self._values.get(namespace)
        if names is None or name not in names:
            raise UnknownSettingError(namespace, name)
        return names[name]


# The types a Setting can be declared as.
_TYPES = ("int", "float", "bool", "str")

_DECLARATION_KEYS = ("type", "default", "description")


class SettingDeclaration:
    """One declared Setting: its type and its default, or none when *required*."""

    __slots__ = ("default", "required", "type_name")

    def __init__(self, type_name: str, default: object = None, required: bool = True) -> None:
        self.type_name = type_name
        self.default = default
        self.required = required


class SettingValueError(ValueError):
    """Setting *setting* cannot take the value given or resolve, for *reason*."""

    def __init__(self, setting: str, reason: str) -> None:
        self.setting = setting
        self.reason = reason
        super().__init__(f"Setting '{setting}': {reason}")


def parse_declarations(section: object) -> dict[str, SettingDeclaration]:
    """Parse a ``settings`` section, ``{name: {"type", "default"?, "description"?}}``.

    A declaration with no ``default`` is required.

    Raises:
        ValueError: the section, or a declaration in it, is malformed; the
            message is the reason, for the caller to wrap with its file.
    """
    if not isinstance(section, dict):
        raise ValueError("'settings' is not an object")
    declarations: dict[str, SettingDeclaration] = {}
    for name, raw in section.items():
        declarations[name] = _parse_declaration(name, raw)
    return declarations


def _parse_declaration(name: str, raw: object) -> SettingDeclaration:
    if not isinstance(raw, dict):
        raise ValueError(f"Setting '{name}' is not an object")
    for key in raw:
        if key not in _DECLARATION_KEYS:
            raise ValueError(f"Setting '{name}' has unknown key {key!r}")
    type_name = raw.get("type")
    if type_name not in _TYPES:
        raise ValueError(f"Setting '{name}' has unknown type {type_name!r}")
    if "description" in raw and not isinstance(raw["description"], str):
        raise ValueError(f"Setting '{name}' has a description that is not a string")
    if "default" not in raw:
        return SettingDeclaration(type_name)
    default = raw["default"]
    if not _matches(type_name, default):
        raise ValueError(f"Setting '{name}' default {default!r} is not a {type_name}")
    return SettingDeclaration(type_name, _coerce(type_name, default), required=False)


def resolve_settings(
    declarations: dict[str, SettingDeclaration], overrides: list[dict[str, object]]
) -> dict[str, object]:
    """Resolve every declared Setting: its default, then each of *overrides* in order.

    Raises:
        SettingValueError: an override names an undeclared Setting or gives a
            value of the wrong type, or a required Setting is left unset.
    """
    resolved: dict[str, object] = {}
    for name, declaration in declarations.items():
        if not declaration.required:
            resolved[name] = declaration.default
    for layer in overrides:
        for name, value in layer.items():
            declaration = declarations.get(name)
            if declaration is None:
                raise SettingValueError(name, "is not declared")
            if not _matches(declaration.type_name, value):
                raise SettingValueError(name, f"{value!r} is not a {declaration.type_name}")
            resolved[name] = _coerce(declaration.type_name, value)
    for name in declarations:
        if name not in resolved:
            raise SettingValueError(name, "is required and was not set")
    return resolved


def _matches(type_name: str, value: object) -> bool:
    # bool is an int subclass in Python, but never a valid int or float Setting.
    if isinstance(value, bool):
        return type_name == "bool"
    if type_name == "int":
        return isinstance(value, int)
    if type_name == "float":
        return isinstance(value, (int, float))
    if type_name == "str":
        return isinstance(value, str)
    return False


def _coerce(type_name: str, value: object) -> object:
    if type_name == "float":
        return float(value)  # type: ignore[arg-type]
    return value
