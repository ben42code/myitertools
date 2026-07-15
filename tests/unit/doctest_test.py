import doctest
import pathlib
import unittest

# The public-API examples live in README.md (single source of truth) and are
# executed here as doctests so they cannot drift from the code. README.md sits
# at the repo root, two levels up from this test module. Read from the checkout
# while the examples import the installed package — so this also validates the
# published artifact when run as a post-publish smoke test.
#
# The examples are run from a regular TestCase (rather than exposed as
# doctest.DocTestCase via load_tests/DocFileSuite) because the VS Code Python
# test adapter skips doctest cases and reports a discovery error for them. A
# plain TestCase is discoverable, runnable and debuggable from Test Explorer,
# while remaining identical for command-line unittest and CI.
_README = pathlib.Path(__file__).resolve().parents[2] / "README.md"


class ReadmeDoctest(unittest.TestCase):
    def test_readme_examples(self):
        failures, _ = doctest.testfile(
            str(_README), module_relative=False, verbose=False
        )
        self.assertEqual(failures, 0, "README.md doctest examples failed")
