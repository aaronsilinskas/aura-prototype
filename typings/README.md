# CircuitPython stubs for type checking

basedpyright reads these instead of the real modules, which exist only on the device. Each stub types every attribute as `Any`, so code that uses a module type-checks without CircuitPython installed, and a misspelled module name is still an error.

When device code imports a new CircuitPython-only module, add `<module>.pyi` here, copying an existing stub. Use a directory with `__init__.pyi` for a package with submodules.
