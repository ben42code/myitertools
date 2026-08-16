# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `SECURITY.md`: supported versions and how to report a vulnerability privately
  ([#64]).
- `CONTRIBUTING.md`: branch, commit, pull request and quality gate conventions
  ([#65]).
- `Issues` link in the package metadata, shown on the PyPI sidebar ([#62]).

## [0.0.7] - 2026-08-13

### Added
- `collapse`: lazily flatten nested iterables, with per-type `handlers` and an
  `atoms` option, resolved most-specific-first (MRO/ABC aware) ([#46]).
- README "Stability" section documenting the SemVer policy, the exact public
  API surface, and the pre-1.0 compatibility caveat ([#44]).

## [0.0.6] - 2026-07-17

### Added
- `IteratorCounter`: a transparent wrapper that counts the values pulled
  through an iterator/iterable, without changing what flows downstream ([#17]).
- `StreamSequence`: a lazy `collections.abc.Sequence` view over a one-shot
  iterator/iterable — positive/negative indexing, slicing, `len()`, iteration,
  and `take()`/`consume()` — while consuming the source on demand ([#26]).
- Public API documentation in the README, with every example verified in CI as
  a doctest ([#36]).
- Automated PyPI/TestPyPI release workflow with tag-derived, PEP 440-validated
  versioning and post-publish smoke tests of the published package ([#28], [#35]).

### Changed
- Require Python >= 3.10 (dropped Python 3.9 support) ([#23]).
- Officially test the full supported matrix in CI: CPython 3.10–3.14 and
  PyPy 3.10–3.11 ([#24], [#27]).
- Consolidate project configuration and dependencies into `pyproject.toml`;
  remove `requirements.txt` ([#16], [#31], [#32]).
- Expand the PyPI trove classifiers (supported Python versions, audience,
  topics) ([#40]).
- Canonicalize the package's public surface: expose exactly `islice_extended`,
  `IteratorCounter`, and `StreamSequence` via an explicit `__all__`, with the
  implementation kept in private modules ([#37], [#39]).

## [0.0.5] - 2025-05-11

Earliest release covered by this changelog; releases prior to 0.0.5 are not
documented here.

### Added
- `islice_extended`: an `itertools.islice` variant that accepts negative
  `start`/`stop` indices and a negative `step`. Supports Python >= 3.9.

[Unreleased]: https://github.com/ben42code/myitertools/compare/v0.0.7...HEAD
[0.0.7]: https://github.com/ben42code/myitertools/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/ben42code/myitertools/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/ben42code/myitertools/releases/tag/v0.0.5
[#16]: https://github.com/ben42code/myitertools/pull/16
[#17]: https://github.com/ben42code/myitertools/pull/17
[#23]: https://github.com/ben42code/myitertools/pull/23
[#24]: https://github.com/ben42code/myitertools/pull/24
[#26]: https://github.com/ben42code/myitertools/pull/26
[#27]: https://github.com/ben42code/myitertools/pull/27
[#28]: https://github.com/ben42code/myitertools/pull/28
[#31]: https://github.com/ben42code/myitertools/pull/31
[#32]: https://github.com/ben42code/myitertools/pull/32
[#35]: https://github.com/ben42code/myitertools/pull/35
[#36]: https://github.com/ben42code/myitertools/pull/36
[#37]: https://github.com/ben42code/myitertools/pull/37
[#39]: https://github.com/ben42code/myitertools/pull/39
[#40]: https://github.com/ben42code/myitertools/pull/40
[#44]: https://github.com/ben42code/myitertools/pull/44
[#46]: https://github.com/ben42code/myitertools/pull/46
[#62]: https://github.com/ben42code/myitertools/pull/62
[#64]: https://github.com/ben42code/myitertools/pull/64
[#65]: https://github.com/ben42code/myitertools/pull/65
