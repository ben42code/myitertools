# Contributing

Thanks for taking a look. This file covers the conventions; see
[README.dev.md](README.dev.md) for the environment, tests, coverage, linting and
release tooling.

## Before you start

For anything beyond a small fix, open an issue first. The public API is
deliberately small, and a primitive is easier to discuss before it is written.

## Branches and commits

- Branch names: `u/<github-user>/<topic>`, e.g. `u/ben42code/add-collapse`.
- Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `build:`, `chore:`.
- Write why the change is needed, not what the diff already shows.

## Pull requests

- **Atomic**: one scope per PR. A feature, a bugfix and a cleanup are three PRs,
  even when they touch the same file.
- **Reviewable in one sitting.** If a change is large, split it into a sequence
  of PRs that each make sense on their own.
- **Tests ship with the code they test**, in the same PR. Later PRs may improve
  them.

## Quality gates

CI enforces all of these, so run them locally first:

- `python -m unittest discover -v -s "tests" -p "*_test.py" -t "."`
- `coverage run -m unittest discover -s "tests" -p "*_test.py" -t "." && coverage report`  
  Coverage must stay at 100% — `fail_under` in `setup.cfg` makes anything less an
  error.
- `python -m flake8 .`
- `python -m isort --check-only --diff .`

The library supports CPython 3.10+ and PyPy; CI runs the full matrix, including
the next Python release before it ships.

## Documentation

- `README.md` examples are `>>>` **doctests** verified in CI — they are the
  single source of truth for how the API behaves. Update them with the code.
  Keep a blank line before the closing fence of a `python` block, or doctest
  reads the fence as expected output.
- They run from a plain `unittest.TestCase` that calls `doctest.testfile(...)`
  and asserts 0 failures. Do not expose them via `load_tests` /
  `doctest.DocFileSuite`: the VS Code Python test adapter skips the resulting
  doctest cases and errors test discovery.
- Add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for
  anything user-visible.

## Design principles

- **Public primitives are general-purpose library APIs.** Design them to be
  robust and broadly capable, not shaped around one caller's use case.
- **Pure Python by design.** Portability (universal wheel, CPython + PyPy,
  zero-build install) and maintainability come before raw performance, and the
  resulting performance ceiling is accepted.
- **Typing**: prefer named aliases over repeating inline type expressions. Use
  `TypeAlias` (PEP 613) while `requires-python` includes 3.10/3.11 — the PEP 695
  `type` statement is 3.12+.

## Reporting a vulnerability

Do not open a public issue; see [SECURITY.md](SECURITY.md).
