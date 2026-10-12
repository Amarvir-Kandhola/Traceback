# Decisions

## 2026-10-12 — Package name `tracebackai`
`traceback` is a stdlib module used by logging, pytest and FastAPI's error handling; a
package with that name would shadow it. The import package is `tracebackai`, the
distribution name `traceback-ai`.

## 2026-10-12 — src/ layout
Code lives in `src/tracebackai/`. With a flat layout, tests can import the package straight
from the working directory even if packaging is broken. With src/, tests only pass against
the installed package, so packaging mistakes surface immediately.

## 2026-10-12 — hatchling as build backend
Minimal config in `pyproject.toml`, no `setup.py`. Alternatives: setuptools (more legacy
configuration surface), poetry/uv build backends (tie the project to a specific tool).

## 2026-10-12 — ruff rules E, F, I, UP, B
pycodestyle errors, pyflakes, import sorting, pyupgrade (modern 3.12 syntax) and bugbear
(likely bugs). A small, uncontroversial set; widen later if useful.
