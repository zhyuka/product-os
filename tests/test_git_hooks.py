"""The push and commit hooks setup-kit installs refuse what they should and let a clean change through.

git_hook_cases.py plants each case in a temp repository and pushes or commits through the hooks, with
this repo's own launcher on PATH.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipIf(os.name == "nt", "the cases link the launcher and run the hooks with sh")
class GitHooksTest(unittest.TestCase):
    def test_each_planted_case(self):
        done = subprocess.run([sys.executable, str(ROOT / "tests" / "git_hook_cases.py")],
                              capture_output=True, text=True, timeout=1200)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-1000:])
        self.assertRegex(done.stdout, r"hook cases: (\d+) of \1 passed")
