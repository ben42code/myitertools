"""Read or bump the ``[project].version`` field in pyproject.toml.

Provides a single source of truth for the project version so the release
workflow does not re-implement parsing. Uses tomlkit to parse and write, which
validates the TOML and preserves the rest of the file's formatting.

Two versioning modes:

* ``set-dev`` / ``set-rc`` append a unique per-run PEP 440 suffix (``.devN`` for
  TestPyPI sandbox builds, ``rcN`` for manual rc dispatches). ``N`` is the GitHub
  run number, needed because package indexes reject re-uploading a version.
* ``set-release`` publishes the tag-derived version of a GitHub Release. The tag
  is validated (canonical PEP 440, base matching pyproject, rc-only
  pre-releases) and any mismatch fails fast before anything is built.

Usage:
    python .github/scripts/version_tool.py get <pyproject_path>
    python .github/scripts/version_tool.py set-dev <run_number> <pyproject_path>
    python .github/scripts/version_tool.py set-rc <run_number> <pyproject_path>
    python .github/scripts/version_tool.py set-release <tag> <pyproject_path> [--prerelease]
"""

from __future__ import annotations

import pathlib
import sys

import tomlkit
from packaging.version import InvalidVersion, Version
from tomlkit.exceptions import TOMLKitError

_USAGE = (
    "usage:\n"
    "  version_tool.py get <pyproject_path>\n"
    "  version_tool.py set-dev <run_number> <pyproject_path>\n"
    "  version_tool.py set-rc <run_number> <pyproject_path>\n"
    "  version_tool.py set-release <tag> <pyproject_path> [--prerelease]"
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


def set_release_version(
    pyproject_path: pathlib.Path, tag: str, prerelease: bool
) -> str:
    """Set the version from a GitHub Release tag, validating it first.

    The tag must be ``v`` + a canonical PEP 440 version whose base matches the
    pinned pyproject version. Full releases must equal the base exactly;
    pre-releases must be a release candidate (``vX.Y.ZrcN``) with no other
    segments. Any mismatch raises SystemExit so the release fails fast.
    """
    if not tag.startswith("v"):
        raise SystemExit(f"Release tag {tag!r} must start with 'v'")
    version_str = tag[1:]

    try:
        parsed = Version(version_str)
    except InvalidVersion:
        raise SystemExit(f"Release tag {tag!r} is not a valid PEP 440 version")

    if str(parsed) != version_str:
        raise SystemExit(
            f"Release tag {tag!r} is not canonical; expected 'v{parsed}'"
        )

    base = _read_version(pyproject_path)
    if parsed.base_version != base:
        raise SystemExit(
            f"Release tag base '{parsed.base_version}' does not match "
            f"pyproject version '{base}'"
        )

    if prerelease:
        is_rc = parsed.pre is not None and parsed.pre[0] == "rc"
        if not is_rc or parsed.is_devrelease or parsed.is_postrelease \
                or parsed.local is not None:
            raise SystemExit(
                f"Pre-release tag {tag!r} must be a release candidate "
                f"'v{base}rcN'"
            )
    elif version_str != base:
        raise SystemExit(
            f"Release tag {tag!r} must be a final version 'v{base}'"
        )

    _write_version(pyproject_path, version_str)
    return version_str


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
    elif command == "set-release":
        args = argv[2:]
        prerelease = "--prerelease" in args
        positionals = [arg for arg in args if arg != "--prerelease"]
        if len(positionals) != 2:
            raise SystemExit(_USAGE)
        tag, pyproject_path = positionals
        version = set_release_version(
            pathlib.Path(pyproject_path), tag, prerelease=prerelease
        )
        print(f"::notice::Building release {version}")
    else:
        raise SystemExit(_USAGE)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv)
