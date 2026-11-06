"""open_items.py, the reconcile skill's runner for rebase.surfaces: its own selftest, run on planted
sources with no settings of yours in reach, and a run from a fixture list with no settings file."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "reconcile" / "scripts" / "open_items.py"
WINDOWS = os.name == "nt"  # read once, before any test plants os.name


class OpenItemsTest(unittest.TestCase):
    def test_selftest(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--selftest"], capture_output=True, text=True, timeout=300)
        # Only the FAIL lines: CI's annotation keeps a failure's last 15 lines, and the PASS lines after them
        # pushed them out. With none, a crash's last lines.
        fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL ")]
        if r.returncode or fails:
            self.fail("\n".join(fails) or "\n".join((r.stdout + r.stderr).strip().splitlines()[-12:]))

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
    shell command. Off Windows, setUp plants what windows-latest has: os.name "nt", a /bin/sh that can't start
    (FileNotFoundError, as CI said), ProgramFiles set to C:\\Program Files with Git for Windows in it, and a Git
    bash on PATH. On Windows the machine's own Git Bash and PATHEXT do it. No Path() in a test: with os.name
    "nt", pathlib makes a WindowsPath."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.oi = load()
        if WINDOWS:
            return
        # Off Windows, C:\Program Files joined with Git\bin\bash.exe is a path in the working folder, so it's
        # planted there.
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmp)
        for bash in (self.tmp / "C:\\Program Files" / "Git" / "bin" / "bash.exe",
                     self.tmp / "Git" / "usr" / "bin" / "bash"):
            bash.parent.mkdir(parents=True)
            os.symlink("/bin/sh", bash)
        real = subprocess.Popen

        def no_bin_sh(args, *a, **k):
            if args and args[0] == "/bin/sh":
                raise FileNotFoundError(2, "The system cannot find the file specified")
            return real(args, *a, **k)

        machine = {"ProgramFiles": "C:\\Program Files",
                   "PATH": str(self.tmp / "Git" / "usr" / "bin") + os.pathsep + os.environ.get("PATH", "")}
        for p in (mock.patch.dict(os.environ, machine), mock.patch.object(self.oi.os, "name", "nt"),
                  mock.patch.object(self.oi.subprocess, "Popen", no_bin_sh)):
            p.start()
            self.addCleanup(p.stop)

    def hidden(self, git_bash=None):
        """os.environ with each place the lookup searches taken away: CLAUDE_CODE_GIT_BASH_PATH (git_bash when
        given), ProgramFiles, and PATH (an empty folder, plus System32 on Windows)."""
        empty = self.tmp / "empty"
        empty.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items()
               if k.upper() not in ("CLAUDE_CODE_GIT_BASH_PATH", "PROGRAMFILES", "PATH")}
        env["PATH"] = str(empty)
        if WINDOWS:
            env["PATH"] += os.pathsep + os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        if git_bash:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash
        return env

    def machine_git_bash(self):
        """The Git Bash windows-latest has: the planted one off Windows, else this machine's."""
        if not WINDOWS:
            return str(self.tmp / "C:\\Program Files" / "Git" / "bin" / "bash.exe")
        found = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH") or os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "bin", "bash.exe")
        if not os.path.isfile(found):
            if "git-bash" in os.environ.get("REQUIRE_SHELLS", ""):
                self.fail(f"no Git Bash at {found}, and REQUIRE_SHELLS wants one")
            self.skipTest(f"no Git Bash at {found}")
        return found

    def run_source(self, cmd, env):
        with mock.patch.dict(os.environ, env, clear=True):
            return self.oi.run_source({"name": "planted", "cmd": cmd}, str(self.tmp), "2026-11-01")

    def test_a_source_runs_in_the_git_bash_its_variable_names(self):
        # ProgramFiles and PATH are hidden, so only CLAUDE_CODE_GIT_BASH_PATH leads to it.
        r = self.run_source('printf "[start now] an item since %s\\n" "$RECONCILE_SINCE"; exit 1',
                            self.hidden(self.machine_git_bash()))
        self.assertEqual(r["items"], [("start now", "an item since 2026-11-01")], r)

    def test_each_route_shown_alone_finds_a_git_bash(self):
        # So the runs here hide routes that work: each one, left visible by itself, leads to a Git Bash.
        bash = self.machine_git_bash()
        if WINDOWS:
            pf, on_path = os.environ.get("ProgramFiles", r"C:\Program Files"), os.path.dirname(bash)
        else:
            pf, on_path = "C:\\Program Files", str(self.tmp / "Git" / "usr" / "bin")
        where = lambda p: os.path.normcase(os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p)))
        routes = {"CLAUDE_CODE_GIT_BASH_PATH": ({"CLAUDE_CODE_GIT_BASH_PATH": bash}, bash),
                  "ProgramFiles": ({"ProgramFiles": pf}, os.path.join(pf, "Git", "bin", "bash.exe")),
                  "PATH": ({"PATH": on_path}, shutil.which("bash", path=on_path) or "(none on PATH)")}
        for route, (shown, expected) in routes.items():
            env = self.hidden()
            env.update(shown)
            got = self.oi.shell(env)
            self.assertEqual(where(got) if got else None, where(expected), route)

    def test_with_every_route_hidden_no_git_bash_did_not_run_and_names_the_fix(self):
        r = self.run_source("exit 1", self.hidden())
        self.assertFalse(r["ran"], r)
        self.assertIn("CLAUDE_CODE_GIT_BASH_PATH", r["why"], r)

    def test_wrap_quotes_a_tool_by_the_name_it_was_given(self):
        # PATHEXT finds python as python.EXE on Windows (CI's selftest quoted cat.EXE); wrap's error names the tool
        # as the list entry gave it. Off Windows the lookup is planted: a python.EXE and a PATHEXT search for it.
        tools = self.tmp / "tools"
        tools.mkdir()
        env = dict(os.environ, PATHEXT=".COM;.EXE")
        if WINDOWS:
            env["PATH"] = os.path.dirname(sys.executable)
            which = shutil.which
        else:
            os.symlink(os.path.realpath(sys.executable), tools / "python.EXE")
            env["PATH"] = str(tools)

            def which(name, mode=os.F_OK | os.X_OK, path=None):
                for d in (path or os.environ.get("PATH", "")).split(os.pathsep):
                    for ext in os.environ.get("PATHEXT", "").split(";"):
                        if os.path.isfile(os.path.join(d, name + ext)):
                            return os.path.join(d, name + ext)
                return None
        err = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(self.oi.shutil, "which", which), redirect_stderr(err):
            code = self.oi.wrap(["--", "python", "-c", "import sys; sys.stderr.write('Error: planted\\n'); sys.exit(1)"])
        self.assertEqual(code, 2, err.getvalue())
        self.assertIn("wrap: python exited 1: Error: planted", err.getvalue())

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
