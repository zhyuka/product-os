"""bin/product-os: it runs a tool with the first python3 or python that actually runs at 3.9 or
later, skips a stub that's on PATH but can't run, and exits 2 with one line when none works."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "bin" / "product-os"


def stub(folder, name, body):
    path = Path(folder, name)
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@unittest.skipIf(os.name == "nt", "the launcher is a sh script; Windows runs it from Git Bash")
class RunnerTest(unittest.TestCase):
    def run_with(self, python3_body, python_body):
        with tempfile.TemporaryDirectory() as tmp:
            if python3_body is not None:
                stub(tmp, "python3", python3_body)
            if python_body is not None:
                stub(tmp, "python", python_body)
            env = dict(os.environ, PATH=f"{tmp}:/usr/bin:/bin")
            return subprocess.run([str(RUNNER), "doctor", "--help"], capture_output=True, text=True, env=env)

    def test_a_python3_stub_that_cant_run_is_skipped(self):
        p = self.run_with("echo 'install the developer tools?' >&2; exit 1", f'exec "{sys.executable}" "$@"')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("usage", p.stdout.lower())

    def test_a_python_older_than_3_9_is_skipped(self):
        old = 'case "$*" in *version_info*) exit 1 ;; esac; exit 0'
        p = self.run_with(old, f'exec "{sys.executable}" "$@"')
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_no_working_python_exits_2_with_one_line(self):
        p = self.run_with("exit 9009", "exit 1")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1, p.stderr)
        self.assertIn("no Python 3.9 or later runs here", p.stderr)


if __name__ == "__main__":
    unittest.main()
