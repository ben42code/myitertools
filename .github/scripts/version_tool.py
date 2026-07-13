"""Read or bump the ``[project].version`` field in pyproject.toml.

Provides a single source of truth for the project version so the release
workflow does not re-implement parsing. Uses tomlkit to parse and write, which
validates the TOML and preserves the rest of the file's formatting.

Package indexes reject re-uploading an existing version, so builds get a unique
per-run PEP 440 suffix: ``.devN`` (``set-dev``, TestPyPI sandbox builds) or
``rcN`` (``set-rc``, GitHub pre-releases published to PyPI as release
candidates). ``N`` is the GitHub run number.

Usage:
    python .github/scripts/version_tool.py get <pyproject_path>
    python .github/scripts/version_tool.py set-dev <run_number> <pyproject_path>
    python .github/scripts/version_tool.py set-rc <run_number> <pyproject_path>
"""

from __future__ import annotations

import pathlib
import sys

import tomlkit
from tomlkit.exceptions import TOMLKitError

_USAGE = (
    "usage:\n"
    "  version_tool.py get <pyproject_path>\n"
    "  version_tool.py set-dev <run_number> <pyproject_path>\n"
    "  version_tool.py set-rc <run_number> <pyproject_path>"
)


def _load(pyproject_path: pathlib.Path) -> tomlkit.TOMLDocument:
    try:
        return tomlkit.parse(pyproject_path.read_text())
    except TOMLKitError as error:
        raise SystemExit(f"Invalid TOML in {pyproject_path}: {error}")


def _read_version(pyproject_path: pathlib.Path) -> str:
    document = _load(pyproject_path)
    try:
        return str(document["project"]["version"])
    except (KeyError, TypeError):
        raise SystemExit(f"No [project].version found in {pyproject_path}")


def get_version(pyproject_path: pathlib.Path) -> str:
    return _read_version(pyproject_path)


def _write_version(pyproject_path: pathlib.Path, version: str) -> None:
    document = _load(pyproject_path)
    document["project"]["version"] = version
    pyproject_path.write_text(tomlkit.dumps(document))


def _set_version(pyproject_path: pathlib.Path, suffix: str) -> str:
    new_version = f"{_read_version(pyproject_path)}{suffix}"
    _write_version(pyproject_path, new_version)
    return new_version


def set_dev_version(pyproject_path: pathlib.Path, run_number: str) -> str:
    return _set_version(pyproject_path, f".dev{run_number}")


def set_rc_version(pyproject_path: pathlib.Path, run_number: str) -> str:
    return _set_version(pyproject_path, f"rc{run_number}")


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit(_USAGE)

    command = argv[1]
    if command == "get":
        if len(argv) != 3:
            raise SystemExit(_USAGE)
        print(get_version(pathlib.Path(argv[2])))
    elif command == "set-dev":
        if len(argv) != 4:
            raise SystemExit(_USAGE)
        dev_version = set_dev_version(pathlib.Path(argv[3]), argv[2])
        print(f"::notice::Building dev version {dev_version}")
    elif command == "set-rc":
        if len(argv) != 4:
            raise SystemExit(_USAGE)
        rc_version = set_rc_version(pathlib.Path(argv[3]), argv[2])
        print(f"::notice::Building release candidate {rc_version}")
    else:
        raise SystemExit(_USAGE)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv)
