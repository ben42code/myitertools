import contextlib
import importlib.util
import io
import os
import pathlib
import tempfile
import unittest

_SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[2] / ".github" / "scripts" / "version_tool.py"
_spec = importlib.util.spec_from_file_location("version_tool", _SCRIPT_PATH)
version_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(version_tool)


class TestVersionTool(unittest.TestCase):
    def _writePyproject(self, body: str) -> pathlib.Path:
        handle, name = tempfile.mkstemp(suffix=".toml")
        os.close(handle)
        path = pathlib.Path(name)
        path.write_text(body)
        self.addCleanup(path.unlink)
        return path

    def test_getVersion_withProjectVersion_returnsVersion(self):
        # arrange
        path = self._writePyproject('[project]\nname = "x"\nversion = "0.0.6"\n')

        # act
        result = version_tool.get_version(path)

        # assert
        self.assertEqual(result, "0.0.6")

    def test_getVersion_withNoProjectTable_raisesSystemExit(self):
        # arrange
        path = self._writePyproject('[build-system]\nrequires = ["flit_core"]\n')

        # act / assert
        with self.assertRaises(SystemExit):
            version_tool.get_version(path)

    def test_getVersion_withNoVersionKey_raisesSystemExit(self):
        # arrange
        path = self._writePyproject('[project]\nname = "x"\n')

        # act / assert
        with self.assertRaises(SystemExit):
            version_tool.get_version(path)

    def test_getVersion_withFormattingVariants_stillParses(self):
        variants = [
            '[project]\nversion="1.2.3"\n',          # no spaces
            "[project]\nversion = '1.2.3'\n",        # single quotes
            '[project]\nversion  =  "1.2.3"\n',      # extra spaces
            '[project]\nversion\t=\t"1.2.3"\n',      # tabs
            '[project]\nversion = "1.2.3"   \n',     # trailing spaces
            '[project]\nversion = "1.2.3"  # note\n',  # trailing comment
        ]
        for body in variants:
            with self.subTest(body=body):
                path = self._writePyproject(body)
                self.assertEqual(version_tool.get_version(path), "1.2.3")

    def test_getVersion_withMalformedToml_raisesSystemExit(self):
        # unquoted value and mismatched quotes are invalid TOML
        for body in ('[project]\nversion =1.2.3\n', '[project]\nversion = "1.2.3\'\n'):
            with self.subTest(body=body):
                path = self._writePyproject(body)
                with self.assertRaises(SystemExit):
                    version_tool.get_version(path)

    def test_setVersion_appendsSuffix(self):
        cases = [
            (version_tool.set_dev_version, "0.0.6.dev42"),
            (version_tool.set_rc_version, "0.0.6rc42"),
        ]
        for set_version, expected in cases:
            with self.subTest(set_version=set_version.__name__):
                # arrange
                path = self._writePyproject('[project]\nversion = "0.0.6"\n')

                # act
                result = set_version(path, "42")

                # assert
                self.assertEqual(result, expected)
                self.assertIn(f'version = "{expected}"', path.read_text())

    def test_setVersion_onlyTouchesProjectVersion(self):
        cases = [
            (version_tool.set_dev_version, "1.2.3.dev7"),
            (version_tool.set_rc_version, "1.2.3rc7"),
        ]
        for set_version, expected in cases:
            with self.subTest(set_version=set_version.__name__):
                # arrange
                path = self._writePyproject(
                    '[project]\nversion = "1.2.3"\n\n[tool.other]\nversion = "9.9.9"\n'
                )

                # act
                set_version(path, "7")

                # assert
                content = path.read_text()
                self.assertIn(f'version = "{expected}"', content)
                self.assertIn('version = "9.9.9"', content)

    def test_setVersion_preservesFormattingAndComments(self):
        cases = [
            (version_tool.set_dev_version, "0.0.6.dev3"),
            (version_tool.set_rc_version, "0.0.6rc3"),
        ]
        for set_version, expected in cases:
            with self.subTest(set_version=set_version.__name__):
                # arrange
                body = (
                    "# top comment\n"
                    "[project]\n"
                    'name = "x"  # inline\n'
                    'version = "0.0.6"\n'
                    'dependencies = []\n'
                )
                path = self._writePyproject(body)

                # act
                set_version(path, "3")

                # assert
                content = path.read_text()
                self.assertIn("# top comment", content)
                self.assertIn('name = "x"  # inline', content)
                self.assertIn("dependencies = []", content)
                self.assertIn(f'version = "{expected}"', content)

    def test_setVersion_withMalformedToml_raisesAndLeavesFileUntouched(self):
        for set_version in (version_tool.set_dev_version, version_tool.set_rc_version):
            with self.subTest(set_version=set_version.__name__):
                # arrange
                original = '[project]\nversion =1.2.3\n'
                path = self._writePyproject(original)

                # act / assert
                with self.assertRaises(SystemExit):
                    set_version(path, "42")
                self.assertEqual(path.read_text(), original)

    def test_main_get_printsVersion(self):
        # arrange
        path = self._writePyproject('[project]\nversion = "0.0.6"\n')

        # act
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            version_tool.main(["prog", "get", str(path)])

        # assert
        self.assertEqual(stdout.getvalue().strip(), "0.0.6")

    def test_main_setCommand_rewritesVersion(self):
        cases = [("set-dev", "0.0.6.dev5"), ("set-rc", "0.0.6rc5")]
        for command, expected in cases:
            with self.subTest(command=command):
                # arrange
                path = self._writePyproject('[project]\nversion = "0.0.6"\n')

                # act
                version_tool.main(["prog", command, "5", str(path)])

                # assert
                self.assertIn(f'version = "{expected}"', path.read_text())

    def test_main_withUnknownCommand_raisesSystemExit(self):
        # act / assert
        with self.assertRaises(SystemExit):
            version_tool.main(["prog", "bogus", "pyproject.toml"])

    def test_main_withNoCommand_raisesSystemExit(self):
        # act / assert
        with self.assertRaises(SystemExit):
            version_tool.main(["prog"])

    def test_main_get_withWrongArgCount_raisesSystemExit(self):
        # act / assert
        with self.assertRaises(SystemExit):
            version_tool.main(["prog", "get"])

    def test_main_setCommand_withWrongArgCount_raisesSystemExit(self):
        # arrange
        path = self._writePyproject('[project]\nversion = "0.0.6"\n')

        # act / assert
        for command in ("set-dev", "set-rc"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    version_tool.main(["prog", command, str(path)])


if __name__ == '__main__':
    unittest.main(verbosity=2)
