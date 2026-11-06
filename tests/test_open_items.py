"""open_items.py, the reconcile skill's runner for rebase.surfaces: its own selftest, run on planted
sources with no settings of yours in reach, and a run from a fixture list with no settings file."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "reconcile" / "scripts" / "open_items.py"


class OpenItemsTest(unittest.TestCase):
    def test_selftest(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--selftest"], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)

    def test_fixture_list(self):
        with tempfile.TemporaryDirectory() as d:
            fixture = Path(d) / "surfaces.json"
            fixture.write_text(json.dumps([
                {"name": "planted", "cmd": "printf '[start now] a planted item\\n'; exit 1"},
                {"name": "broken", "cmd": "echo 'Error: no store' >&2; exit 2"},
            ]), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), "--surfaces", str(fixture), "--project", d],
                               capture_output=True, text=True, timeout=60, cwd=d)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("    [start now] a planted item", r.stdout)
        self.assertIn("DID NOT RUN  broken: exit 2: Error: no store", r.stdout)
        self.assertIn("total 1, listed 1, skipped 0, uncovered 1 (broken)", r.stdout)


if __name__ == "__main__":
    unittest.main()
