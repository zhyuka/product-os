"""open_items.py, the reconcile skill's runner for rebase.surfaces: its own selftest, run on planted
sources with no settings of yours in reach, and a run from a fixture list with no settings file."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def load():
    spec = importlib.util.spec_from_file_location("open_items_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AsOnWindowsTest(unittest.TestCase):
    """Windows has no /bin/sh, so a source's cmd runs in Git Bash, found as Claude Code finds it for a hook's
    shell command: CLAUDE_CODE_GIT_BASH_PATH first. Planted here: os.name is "nt", /bin/sh can't be started (as
    CI's Windows runs said, FileNotFoundError), and CLAUDE_CODE_GIT_BASH_PATH names a stand-in bash."""

    def run_as_windows(self, cmd, bash_path):
        oi = load()
        real = subprocess.Popen

        def no_bin_sh(args, *a, **k):
            if args and args[0] == "/bin/sh":
                raise FileNotFoundError(2, "The system cannot find the file specified")
            return real(args, *a, **k)

        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_GIT_BASH_PATH"}
        env["PATH"] = os.path.dirname(bash_path or "/nowhere/bash")  # no Git bash found on PATH either
        if bash_path:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = bash_path
        with mock.patch.object(oi.os, "name", "nt"), mock.patch.object(oi.subprocess, "Popen", no_bin_sh), \
                mock.patch.dict(os.environ, env, clear=True):
            return oi.run_source({"name": "planted", "cmd": cmd}, os.path.dirname(bash_path or SCRIPT), "2026-11-01")

    def test_a_source_runs_in_git_bash(self):
        with tempfile.TemporaryDirectory() as d:
            bash = Path(d) / "bash.exe"
            bash.write_text(f"#!/bin/sh\necho ran > '{d}/used'\nexec /bin/sh \"$@\"\n", encoding="utf-8")
            bash.chmod(0o755)
            r = self.run_as_windows('printf "[start now] an item since %s\\n" "$RECONCILE_SINCE"; exit 1', str(bash))
            self.assertTrue((Path(d) / "used").exists(), r)
        self.assertEqual(r["items"], [("start now", "an item since 2026-11-01")], r)

    def test_no_git_bash_did_not_run_and_names_the_fix(self):
        r = self.run_as_windows("exit 1", None)
        self.assertFalse(r["ran"], r)
        self.assertIn("CLAUDE_CODE_GIT_BASH_PATH", r["why"], r)

    @unittest.skipUnless(os.name == "nt", "PATHEXT is Windows' own lookup")
    def test_wrap_starts_a_tool_found_by_pathext(self):
        # wrap runs its tool with no shell; a .cmd tool (az is az.cmd) starts only once PATHEXT finds it.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "planted_tool.cmd").write_text("@echo [start now] a planted item\r\n", encoding="utf-8")
            env = dict(os.environ, PATH=d + os.pathsep + os.environ.get("PATH", ""))
            r = subprocess.run([sys.executable, str(SCRIPT), "wrap", "--", "planted_tool"], capture_output=True,
                               text=True, timeout=60, env=env)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "[start now] a planted item"), r.stderr)


if __name__ == "__main__":
    unittest.main()
