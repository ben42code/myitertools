---
name: repo-health-check
description: Assess the repository state including unit tests, test coverage, linting, and Python version compatibility. Use this when asked to check repo health, quality, or status.
---

Run the following checks and report results in a summary table:

## Unit Tests
- If a `.venv*` virtual environment exists, activate the one with the most recent Python version (e.g. `.venv314\Scripts\Activate.ps1` on Windows, `source .venv314/bin/activate` on Linux/macOS)
- Run: `python -m unittest discover -v -s "tests" -p "*_test.py" -t "."`
- If multiple Python versions are available (use `py --list`), run tests on each version that satisfies the `requires-python` constraint in `pyproject.toml`

## Test Coverage
- Run: `coverage run -m unittest discover -s "tests" -p "*_test.py" -t "."`
- Report: `coverage report --show-missing`
- Note any modules with less than 100% branch coverage

## Linting
- Run: `python -m flake8 .`
- Report any violations

## Summary
Present results as a table with: check name, status (pass/fail), and details.
