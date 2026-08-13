# Copilot Instructions

## Git Commits
- Do NOT add `Co-authored-by` trailers to commit messages.

## Pull Requests
- Create atomic PRs — don't mix scopes (feature, bugfix, improvement) in the same PR.
- PRs should be humanly reviewable — split work into PRs small enough to review in one sitting.
- Unit tests ship with the code they test in the same PR.
- Subsequent PRs may improve tests.

## Quality
- The repo health check should be successful at the head of the current branch.

## Design
- Public primitives are general-purpose library APIs: design them to be robust, principled, and broadly capable, not tailored to a single caller's use case.
- Keep the package pure-Python by design: prioritize portability (universal wheel, CPython + PyPy, zero-build install) and maintainability over raw performance, accepting the resulting performance ceiling.

## Typing
- Prefer explicit, centralized type definitions: extract repeated inline type expressions into named aliases rather than duplicating them.
- Use `TypeAlias` (PEP 613) while `requires-python` includes 3.10/3.11; the PEP 695 `type` statement is 3.12+ only.

## Testing
- README.md code examples are `>>>` doctests, verified in CI as the single source of truth.
- Run them from a plain `unittest.TestCase` that calls `doctest.testfile(...)` and asserts 0 failures — do NOT expose them via `load_tests`/`doctest.DocFileSuite`, because the VS Code Python test adapter skips doctest cases and errors test discovery.
- In a `python` doctest block, keep a blank line before the closing ``` fence, or doctest treats the fence as expected output.

