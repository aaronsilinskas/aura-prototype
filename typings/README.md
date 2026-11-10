# Local stubs for type checking

mypy reads these (`mypy_path` in `pyproject.toml`) for device-only modules that `circuitpython-stubs` doesn't cover: the `adafruit_*` driver libraries and `neopixel`. Each stub types every attribute as `Any`, so code that uses a module type-checks without the library installed, and a misspelled module name is still an error.

CircuitPython's core modules (`board`, `busio`, `pulseio`, …) come from `circuitpython-stubs` instead. Don't add a local stub for a module that package provides: a stub here shadows the real one.

The one deliberate exception is `micropython`: the host-only `micropython.py` at the repo root shadows the package's stub, which lacks `native`. Its docstring says why.

When device code imports a new driver library, add `<module>.pyi` here, copying an existing stub. Use a directory with `__init__.pyi` for a package with submodules.
