"""Regression: prepared standalone translations do not require a secondary PAK."""
import importlib.util
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("package_diagnostics", ROOT / "tools/pipeline/package_diagnostics.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class RequiredFilesTests(unittest.TestCase):
    def test_profile_requires_primary_but_not_secondary(self):
        disc = tomllib.loads((ROOT / "games/gow1/game.toml").read_text(encoding="utf-8"))["disc"]
        required = package.required_disc_files(disc)
        self.assertIn(disc["paks"][0], required)
        self.assertNotIn(disc["paks"][1], required)
        self.assertTrue({".disc_layout", disc["toc"], disc["iop_modules_dir"]}.issubset(required))

    def test_names_come_from_profile(self):
        self.assertEqual(package.required_disc_files({"toc": "index", "paks": ["first", "second"], "iop_modules_dir": "modules"}),
                         [".disc_layout", "index", "first", "modules"])


if __name__ == "__main__":
    unittest.main()
