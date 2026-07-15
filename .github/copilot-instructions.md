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

## Testing
- README.md code examples are `>>>` doctests, verified in CI as the single source of truth.
- Run them from a plain `unittest.TestCase` that calls `doctest.testfile(...)` and asserts 0 failures — do NOT expose them via `load_tests`/`doctest.DocFileSuite`, because the VS Code Python test adapter skips doctest cases and errors test discovery.
- In a `python` doctest block, keep a blank line before the closing ``` fence, or doctest treats the fence as expected output.

