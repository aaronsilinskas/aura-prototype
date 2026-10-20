---
name: code-quality
description: "Review and guide implementation code against a general quality bar: readability, right-sized optimization, public-API discipline, and type coverage. Use when writing or reviewing production source (not tests, which is the `test-quality` skill; not comments, which is the `comments` skill), when asked whether an implementation is clean/safe/well-shaped, or as an implementation review pass. Language-agnostic; platform- and language-specific rules load from the reference files only when relevant."
argument-hint: "file or function to review or implement"
---

# Code Quality

The general quality bar for implementation code. Three neighbouring dimensions have their own skills. Reach for them rather than duplicating their guidance here:

- **Tests**: `test-quality` (the test quality bar) and `tdd` (writing code test-first)
- **Comments & docstrings**: `comments` (whether and how to document)
- **Module shape**: `codebase-design` (interfaces, seams, deep modules)

This skill covers what's left: the readability and correctness bar for the implementation itself.

## Project Context

Before applying any guidance from this skill, read the project's own sources:

- `GLOSSARY.md` (if it exists), so names use the project's domain language.
- The ADRs under `docs/adr/` that touch the area you're working in.
- Every file in the repo that documents how code should be written. When `CODING_STANDARDS.md`, `CONTRIBUTING.md`, `AGENTS.md` or `CLAUDE.md` exists, it must be on the list.

Treat these as authoritative. They extend the general guidance below and, on any conflict, override it. This applies in particular to target runtime versions, listed hot paths, and project-level conventions.

## Guiding Principle

Readability is the default. Apply performance discipline only where a real constraint demands it, such as hot paths, inner loops, and constrained hardware (see the platform reference files). Everywhere else, never trade clarity for micro-optimizations that don't demonstrably matter.

## Use the Public API

Do not reach into another module's private state (names conventionally marked private, e.g. a leading underscore in Python) to make code or a demo work. Use only the public interface. If the public interface is insufficient, expand it deliberately rather than reaching around it. A missing public affordance is a design signal, not something to bypass.

The one exception is a test that is explicitly exercising internal behaviour (e.g. asserting a private field after calling a public method). Even then, isolate the access to a dedicated helper rather than scattering it.

This is the implementation-side consequence of treating the interface as the test surface. See `codebase-design` for the design rationale (deep modules, seams), and `test-quality` and `tdd` for the testing side (assert through the public interface).

## Comments

The `comments` skill covers comment discipline: the "naming → test → comment" ordering, and never writing prose that restates what the code already says. Apply it to all changed source.

## Type Coverage

Type hints (or the language's equivalent) are required for all function and method parameters and return values. Use narrowly-scoped exceptions only when a concrete constraint makes precise typing impractical, and even then annotate with the best available fallback and note *why* precise typing isn't possible at that location. Platform-specific typing exceptions (e.g. incomplete hardware stubs) live in the reference files.

## Platform- and Language-Specific Rules

The guidance above is general. Load the matching reference file when the target applies:

- CircuitPython / MicroPython (constrained hardware): [embedded-python.md](embedded-python.md)

## Checklist

- [ ] Project context (glossary, relevant ADRs, standards files) read and applied
- [ ] Readability preserved; optimizations confined to where a real constraint demands them
- [ ] No reaching into another module's private state. Only the public interface is used (or a deliberate interface expansion), with the narrow test-helper exception isolated.
- [ ] Comment discipline applied per the `comments` skill
- [ ] All function/method parameters and return types annotated (except documented, justified edge cases)
- [ ] Any applicable platform reference file (e.g. `embedded-python.md`) has been applied
