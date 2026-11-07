"""product-os check with no folder runs the project's own checks, and product-os prove.

A check counts only once it has failed its planted bad cases and passed its good ones, and
a project can add checks but not take one away or change one.
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from product_os import hooks, project
from product_os.cli import main

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "project"
NO_PRINT = {"name": "no-print", "run": "{python} checks/no_print.py {target}", "target": "src",
            "bad": "checks/cases/no-print/bad", "good": "checks/cases/no-print/good"}
NEVER_OBJECTS = {**NO_PRINT, "run": ["{python}", "-c", "import sys; sys.exit(0)", "{target}"]}
ALWAYS_OBJECTS = {**NO_PRINT, "run": ["{python}", "-c", "import sys; sys.exit(1)", "{target}"]}
GIT = shutil.which("git")


class ProjectTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "shop"
        shutil.copytree(EXAMPLE, self.root, ignore=shutil.ignore_patterns("product-os-checks-proofs.json"))
        self.user = Path(tmp.name).resolve() / "config"
        self.user.mkdir()
        self.env = {"CLAUDE_CONFIG_DIR": str(self.user)}

    def configure(self, *checks, **fields):
        (self.root / ".claude" / "product-os-checks.json").write_text(json.dumps({"checks": list(checks), **fields}))

    def accept(self, *checks):
        (self.user / "product-os-checks.json").write_text(json.dumps(
            {"projects": {str(self.root): {"checks": list(checks)}}}))

    # These run the checks as CI does, with --run-listed, so the project's proof records count.
    # LocalTest covers a person's own machine, where a check runs only once accepted.
    def statuses(self, run_listed=True, **kw):
        return {r.check: r.status for r in
                project.check_project(self.root, self.env, run_listed=run_listed, **kw)[0]}

    def details(self, run_listed=True, **kw):
        return {r.check: r.detail for r in
                project.check_project(self.root, self.env, run_listed=run_listed, **kw)[0]}

    def prove(self, *names, **kw):
        return project.prove_project(self.root, names, self.env, **kw)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env), redirect_stdout(out), redirect_stderr(err):
            code = main([*args, "--project", str(self.root)])
        return code, out.getvalue(), err.getvalue()

    def plant(self):
        shutil.copy(self.root / "checks/cases/no-print/bad/app.py", self.root / "src" / "app.py")


class ProveTest(ProjectTest):
    def test_a_check_counts_only_once_it_is_proven(self):
        code, out, _ = self.cli("check", "--run-listed")
        self.assertEqual(code, 1)
        self.assertIn("unproven", out)
        self.assertIn("stop and say you are blocked", out)
        code, out, _ = self.cli("prove")
        self.assertEqual(code, 0, out)
        self.assertIn("1 of 1            1 of 1             proven", out)
        self.assertEqual(self.cli("check", "--run-listed")[0], 0)
        self.plant()
        code, out, _ = self.cli("check", "--run-listed")
        self.assertEqual(code, 1)
        self.assertIn("calls print(); use the logger", out)

    def test_prove_fails_a_check_that_never_objects_or_always_does(self):
        # The same calibration the checks are held to: catch the planted bad case, pass the good one.
        self.configure({**NEVER_OBJECTS, "name": "never"}, {**ALWAYS_OBJECTS, "name": "always"}, NO_PRINT)
        rows, _, ok = self.prove()
        self.assertFalse(ok)
        results = {row[0]: row[1:] for row in rows}
        self.assertEqual(results["never"][:2], ["0 of 1", "1 of 1"])
        self.assertIn("it passed the bad case checks/cases/no-print/bad", results["never"][2])
        self.assertEqual(results["always"][:2], ["1 of 1", "0 of 1"])
        self.assertIn("it failed the good case checks/cases/no-print/good", results["always"][2])
        self.assertEqual(results["no-print"], ["1 of 1", "1 of 1", "proven"])
        self.assertEqual(self.statuses(), {"never": "unproven", "always": "unproven", "no-print": "pass"})
        self.assertEqual(set(project.read_proofs(self.root)), {"no-print"})

    def test_a_proof_that_stops_holding_drops_its_record(self):
        self.assertTrue(self.prove()[2])
        (self.root / "checks/cases/no-print/good/app.py").write_text("print('now the good case fails')\n")
        self.assertFalse(self.prove()[2])
        self.assertEqual(project.read_proofs(self.root), {})

    def test_a_change_to_the_check_or_a_case_leaves_it_unproven(self):
        self.assertTrue(self.prove()[2])
        script = self.root / "checks" / "no_print.py"
        original = script.read_text()
        script.write_text(original.replace("return 1 if found else 0", "return 0"))
        self.assertEqual(self.statuses(), {"no-print": "unproven"})
        self.assertIn("the check changed since it was proven", self.details()["no-print"])
        self.assertFalse(self.prove()[2], "the weakened check passes its bad case")
        script.write_text(original)
        self.assertTrue(self.prove()[2])
        case = self.root / "checks/cases/no-print/bad/app.py"
        case.write_text(case.read_text() + "# edited\n")
        self.assertIn("the case checks/cases/no-print/bad changed", self.details()["no-print"])
        self.assertTrue(self.prove()[2])
        self.configure({**NO_PRINT, "target": "."})
        self.assertIn("the check changed", self.details()["no-print"])

    def test_a_change_inside_a_folder_the_check_names_leaves_it_unproven(self):
        # The check reads its banned words from checks/rules/. Deleting a rule weakens it.
        rules = self.root / "checks" / "rules"
        rules.mkdir()
        (rules / "print.txt").write_text("print(\n")
        scan = ("import pathlib, sys; words = [w for f in sorted(pathlib.Path(sys.argv[1]).iterdir())"
                " for w in f.read_text().split()]; sys.exit(any(w in p.read_text() for p in"
                " pathlib.Path(sys.argv[2]).rglob('*.py') for w in words))")
        self.configure({**NO_PRINT, "run": ["{python}", "-c", scan, "checks/rules", "{target}"]})
        self.assertTrue(self.prove()[2])
        self.assertEqual(self.statuses(), {"no-print": "pass"})
        (rules / "print.txt").unlink()
        self.assertEqual(self.statuses(), {"no-print": "unproven"})
        self.assertFalse(self.prove()[2], "with no rules, the check passes its bad case")

    def test_the_files_that_define_a_check(self):
        design = self.root / "design"
        design.mkdir()
        (design / "index.json").write_text("{}")
        other = self.root / "approved"
        other.mkdir()
        (other / "index.json").write_text("{}")
        exercise = ["{python}", "-m", "product_os", "design", "exercise", "--serve",
                    "{target}", "/"]

        def named(run, target="dist"):
            check = project.parse([{**NO_PRINT, "run": run, "target": target}], "test", "test")[0]
            return [p.relative_to(self.root).as_posix() for p in project.named_files(check, self.root)]

        self.assertEqual(named(exercise), ["design/index.json"])
        self.assertEqual(named(exercise + ["--baseline", "approved"]), ["approved/index.json"])
        self.assertEqual(named(exercise + ["--baseline=approved"]), ["approved/index.json"])
        self.assertEqual(named(["{python}", "checks/no_print.py", "checks", "src", "{target}"],
                               target="src"),
                         ["checks/no_print.py", "checks/cases/no-print/bad/app.py",
                          "checks/cases/no-print/good/app.py"],
                         "a folder that holds the target is left out, and a file is listed once")

    def test_a_word_no_path_can_hold_names_no_file(self):
        # An inline `python -c` program is a word Python 3.9's resolve() raises on, on Windows,
        # and a NUL makes every Python raise. Such a word names no file, and the rest still count.
        def named(run):
            check = project.parse([{**NO_PRINT, "run": run}], "test", "test")[0]
            return [p.relative_to(self.root).as_posix() for p in project.named_files(check, self.root)]

        inline = ["{python}", "-c", "import sys; sys.exit(0)", "checks/no_print.py", "{target}"]
        self.assertEqual(named(inline + ["a\0b"]), ["checks/no_print.py"])
        real = Path.resolve

        def windows_39(path, *args, **kwargs):
            if ";" in path.name:
                raise OSError(22, "The filename, directory name, or volume label syntax is incorrect",
                              str(path), 123)
            return real(path, *args, **kwargs)

        with mock.patch.object(Path, "resolve", windows_39):
            self.assertEqual(named(inline), ["checks/no_print.py"])

    def test_check_prove_runs_the_cases_instead_of_trusting_the_record(self):
        # A record can be written by hand. --prove, which CI runs, runs the cases again.
        self.configure(NEVER_OBJECTS)
        [check] = project.plan(self.root, self.env).checks
        forged = [(path, must, project.Run(1 if must == "fail" else 0, "")) for path, must in check.cases()]
        project.write_proofs(self.root, {"no-print": project.record(check, self.root, forged)})
        self.assertEqual(self.statuses(), {"no-print": "pass"})
        self.assertEqual(self.statuses(reprove=True), {"no-print": "unproven"})
        self.assertIn("it passed the bad case", self.details(reprove=True)["no-print"])
        self.assertEqual(self.cli("check", "--prove", "--run-listed")[0], 1)

    def test_check_prove_also_needs_a_current_record(self):
        self.assertEqual(self.statuses(reprove=True), {"no-print": "unproven"})
        self.assertTrue(self.prove()[2])
        self.assertEqual(self.statuses(reprove=True), {"no-print": "pass"})

    def test_a_case_that_is_missing_or_cannot_run_proves_nothing(self):
        self.configure({**NO_PRINT, "bad": ["checks/cases/no-print/bad", "checks/cases/gone"]})
        self.assertIn("the case checks/cases/gone doesn't exist", self.prove()[0][0][-1])
        self.configure({**NO_PRINT, "run": "no-such-program-for-product-os {target}"})
        self.assertIn("no-such-program-for-product-os was not found", self.prove()[0][0][-1])
        self.configure({**NO_PRINT, "run": ["{python}", "-c", "import time; time.sleep(30)", "{target}"],
                        "timeout": 0.5})
        self.assertIn("timed out after 0.5 s", self.prove()[0][0][-1])

    def test_the_shipped_example_is_proven_and_passes(self):
        code, out = self.run_in_example("check", "--prove", "--run-listed")
        self.assertEqual(code, 0, out)
        self.assertIn("1 of 1 checks passed", out)

    def run_in_example(self, *args):
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env), redirect_stdout(out), redirect_stderr(io.StringIO()):
            return main([*args, "--project", str(EXAMPLE)]), out.getvalue()


class LocalTest(ProjectTest):
    """On a person's own machine a check runs only once they accepted it, as it is now."""

    # no_print.py, run so that it also leaves ran.txt in the project when it runs
    MARKED = {**NO_PRINT, "run": [
        "{python}", "-c", "import pathlib, runpy, sys; pathlib.Path('ran.txt').touch(); "
        "sys.argv = ['no_print.py', sys.argv[1]]; runpy.run_path('checks/no_print.py', "
        "run_name='__main__')", "{target}"]}

    def ran(self):
        marker = self.root / "ran.txt"
        found = marker.exists()
        if found:
            marker.unlink()
        return found

    def setUp(self):
        super().setUp()
        self.configure(self.MARKED)
        self.assertTrue(self.prove()[2])  # the project's own record is current
        self.ran()

    def test_a_listed_check_with_a_current_record_doesnt_run_until_accepted(self):
        code, out, _ = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("not accepted on this machine, so it didn't run", out)
        self.assertFalse(self.ran(), "the project's check ran without being accepted")
        self.assertEqual(self.statuses(run_listed=False, reprove=True), {"no-print": "unproven"})
        self.assertFalse(self.ran(), "check --prove ran an unaccepted check's cases")

    def test_accept_shows_the_command_proves_it_and_then_check_runs_it(self):
        code, out, _ = self.cli("accept")
        self.assertEqual(code, 0, out)
        self.assertIn("  no-print: {python} -c 'import pathlib, runpy", out)
        self.assertIn("proven and accepted", out)
        self.ran()
        code, out, _ = self.cli("check")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.ran())
        self.plant()
        self.assertEqual(self.cli("check")[0], 1)

    def test_an_accepted_check_that_changes_stops_running(self):
        self.assertEqual(self.cli("accept")[0], 0)
        self.configure({**self.MARKED, "target": "."})
        self.ran()
        code, out, _ = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("the check changed since it was accepted, so it didn't run", out)
        self.assertFalse(self.ran())

    def test_acceptance_is_for_one_project_folder(self):
        self.assertEqual(self.cli("accept")[0], 0)
        copy = self.root.parent / "shop-copy"
        shutil.copytree(self.root, copy)
        results = project.check_project(copy, self.env)[0]
        self.assertEqual([(r.check, r.status) for r in results], [("no-print", "unproven")])
        accepted = json.loads((self.user / "product-os-checks-accepted.json").read_text())
        self.assertEqual(list(accepted["projects"]), [Path(os.path.realpath(self.root)).as_posix()])

    @unittest.skipUnless(GIT, "needs git")
    def test_acceptance_covers_the_repositorys_worktrees_but_not_a_clone(self):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "shop", "--no-verify"]):
            subprocess.run([GIT, "-C", str(self.root), *args], check=True, env=env, capture_output=True)
        self.assertEqual(self.cli("accept")[0], 0)
        worktree, clone = self.root.parent / "shop-fix", self.root.parent / "shop-clone"
        subprocess.run([GIT, "-C", str(self.root), "worktree", "add", "-q", str(worktree)], check=True,
                       env=env, capture_output=True)
        subprocess.run([GIT, "clone", "-q", str(self.root), str(clone)], check=True, env=env, capture_output=True)
        statuses = {name: {r.check: r.status for r in project.check_project(path, self.env)[0]}
                    for name, path in (("worktree", worktree), ("clone", clone))}
        self.assertEqual(statuses, {"worktree": {"no-print": "pass"}, "clone": {"no-print": "unproven"}})
        accepted = json.loads((self.user / "product-os-checks-accepted.json").read_text())
        self.assertEqual(list(accepted["projects"]),
                         [f"git:{Path(os.path.realpath(self.root / '.git')).as_posix()}:."])

    @unittest.skipUnless(GIT, "needs git")
    def test_an_older_record_kept_by_path_still_counts(self):
        self.assertEqual(self.cli("accept")[0], 0)  # not a git repository yet: kept by path
        subprocess.run([GIT, "-C", str(self.root), "init", "-q"], check=True, capture_output=True)
        subprocess.run([GIT, "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-q", "--allow-empty", "-m", "start", "--no-verify"], check=True, capture_output=True)
        self.ran()
        code, out, _ = self.cli("check")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.ran())

    def test_run_listed_runs_every_listed_check_on_the_projects_record(self):
        code, out, _ = self.cli("check", "--run-listed")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.ran())


class ProveFirstTest(ProjectTest):
    """prove --check: Claude Code asks the user before an agent writes in .claude/, so an agent
    proves a new check from its own file and the user lists a check that is already proven."""

    def entry_file(self, data):
        path = self.root / "checks" / "candidate.json"
        path.write_text(json.dumps(data))
        return str(path)

    def test_a_check_proven_from_its_own_file_counts_once_listed_unchanged(self):
        self.configure()
        for data in (NO_PRINT, {"checks": [NO_PRINT]}, [NO_PRINT]):
            code, out, _ = self.cli("prove", "--check", self.entry_file(data))
            self.assertEqual(code, 0, out)
            self.assertIn("1 of 1            1 of 1             proven", out)
            self.assertIn("counts once it is listed", out)
        self.assertEqual(self.statuses(), {}, "a check that isn't listed doesn't run")
        self.configure(NO_PRINT)
        self.assertEqual(self.statuses(), {"no-print": "pass"})

    def test_a_listing_that_differs_from_the_proven_entry_is_unproven(self):
        self.configure()
        self.assertEqual(self.cli("prove", "--check", self.entry_file(NO_PRINT))[0], 0)
        self.configure({**NO_PRINT, "target": "."})
        self.assertIn("the check changed since it was proven", self.details()["no-print"])

    def test_a_check_that_never_objects_is_not_proven_from_its_file_either(self):
        self.configure()
        code, out, _ = self.cli("prove", "--check", self.entry_file({**NEVER_OBJECTS, "name": "never"}))
        self.assertEqual(code, 1)
        self.assertIn("it passed the bad case checks/cases/no-print/bad", out)
        self.assertEqual(project.read_proofs(self.root), {})

    def test_a_file_cannot_reuse_a_listed_checks_name_for_another_check(self):
        # Records are kept by name, so a different check under a listed name would replace its record.
        self.assertTrue(self.prove()[2])
        before = project.read_proofs(self.root)
        code, _, err = self.cli("prove", "--check", self.entry_file(NEVER_OBJECTS))
        self.assertEqual(code, 2)
        self.assertIn("a different check named 'no-print' is already listed", err)
        self.assertEqual(project.read_proofs(self.root), before)
        self.assertEqual(self.statuses(), {"no-print": "pass"})
        self.assertEqual(self.cli("prove", "--check", self.entry_file(NO_PRINT))[0], 0, "the same entry is fine")

    def test_a_broken_file_is_exit_2_and_check_does_not_mix_with_names(self):
        path = self.root / "checks" / "candidate.json"
        path.write_text("{not json")
        code, _, err = self.cli("prove", "--check", str(path))
        self.assertEqual(code, 2)
        self.assertIn("could not be read", err)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            main(["prove", "no-print", "--check", str(path)])
        self.assertEqual(stop.exception.code, 2)


class ConfigTest(ProjectTest):
    def test_a_project_with_no_checks_does_not_pass(self):
        self.configure()
        code, out, _ = self.cli("check")
        self.assertEqual(code, 1)
        self.assertIn("no checks", out)
        self.assertEqual(self.cli("prove")[0], 1)

    def test_a_broken_check_list_is_exit_2_and_named(self):
        cases = {
            "has to name {target}": {**NO_PRINT, "run": "{python} checks/no_print.py src"},
            "unknown field 'expect'": {**NO_PRINT, "expect": "fail"},
            "\"bad\" must name at least one": {**NO_PRINT, "bad": []},
            "\"good\" must name at least one": {k: v for k, v in NO_PRINT.items() if k != "good"},
            "needs a \"name\"": {**NO_PRINT, "name": "../x"},
            "\"run\" can't be split": {**NO_PRINT, "run": "'{target}"},
            "\"timeout\" must be": {**NO_PRINT, "timeout": True},
        }
        for message, entry in cases.items():
            with self.subTest(message=message):
                self.configure(entry)
                code, _, err = self.cli("check")
                self.assertEqual(code, 2)
                self.assertIn(message, err)
        self.configure(NO_PRINT, NO_PRINT)
        self.assertIn("two checks are named 'no-print'", self.cli("prove")[2])
        (self.root / ".claude" / "product-os-checks.json").write_text('{"checks": {}}')
        self.assertIn("must be a list", self.cli("check")[2])

    def test_the_hooks_accept_a_project_file_with_checks(self):
        self.assertEqual(hooks.project_file(self.root)[1], "")
        self.configure(NO_PRINT, builder_agents=["main"])
        self.assertEqual(hooks.load_config(self.root, self.env)[0]["builder_agents"], ["*builder*", "main"])
        (self.root / ".claude" / "product-os-checks.json").write_text('{"checks": "no-print"}')
        self.assertIn("\"checks\" must be a list", hooks.project_file(self.root)[1])

    def test_a_user_entry_can_hold_only_checks(self):
        self.accept(NO_PRINT)
        self.assertEqual(hooks.accepted_qa_commands(self.root, self.env)[0], None)
        self.assertEqual(hooks.load_config(self.root, self.env), ({**hooks.DEFAULTS}, ""))
        (self.user / "product-os-checks.json").write_text(json.dumps({"projects": {str(self.root): {}}}))
        self.assertIn("so no QA command counts", hooks.load_config(self.root, self.env)[1])
        self.assertEqual(self.cli("check")[0], 2, "a broken user file means the required checks are unknown")

    @unittest.skipUnless(GIT, "needs git")
    def test_an_entry_for_the_main_checkout_covers_its_worktrees_not_a_clone(self):
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "shop", "--no-verify"],
                     ["worktree", "add", "-q", str(self.root.parent / "fix-17")]):
            subprocess.run([GIT, "-C", str(self.root), *args], check=True, env=env, capture_output=True)
        subprocess.run([GIT, "clone", "-q", str(self.root), str(self.root.parent / "shop-clone")],
                       check=True, env=env, capture_output=True)
        (self.user / "product-os-checks.json").write_text(json.dumps(
            {"projects": {str(self.root): {"qa_commands": ["npm run check"]}}}))
        self.assertEqual(hooks.accepted_qa_commands(self.root.parent / "fix-17", self.env)[0], ["npm run check"])
        self.assertIsNone(hooks.accepted_qa_commands(self.root.parent / "shop-clone", self.env)[0])


class TrustTest(ProjectTest):
    """The 0.3.6 rule for the hook settings, applied to checks: add, never remove or redefine."""

    def test_the_users_checks_always_run_and_win_over_the_projects(self):
        self.accept(NO_PRINT)
        self.configure({**NEVER_OBJECTS}, {**NO_PRINT, "name": "extra", "target": "src/app.py"})
        work = project.plan(self.root, self.env)
        self.assertEqual([(c.name, c.source) for c in work.checks], [("no-print", "yours"), ("extra", "project")])
        self.assertEqual(work.checks[0].run[1], "checks/no_print.py")
        self.assertIn("differs from the one in your own product-os-checks.json, so yours runs", work.notes[0])
        self.assertTrue(self.prove()[2])
        self.plant()
        self.assertEqual(self.statuses(), {"no-print": "fail", "extra": "fail"})
        self.configure()  # taking it out of the project file doesn't remove it either
        self.assertEqual(self.statuses(), {"no-print": "fail"})


@unittest.skipUnless(GIT, "git is not installed")
class BaseTest(ProjectTest):
    """With --base REF, the checks the project had at REF stay, with their cases unchanged."""

    def setUp(self):
        super().setUp()
        self.git("init", "-q", "-b", "main")
        self.assertTrue(self.prove()[2])
        self.commit("Add the no-print check")
        self.git("checkout", "-q", "-b", "change")

    def git(self, *args, stdin=""):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "commit.gpgsign=false", *args], cwd=str(self.root), check=True,
                              input=stdin, capture_output=True, text=True).stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_a_change_that_keeps_the_checks_passes(self):
        self.assertEqual(self.statuses(base="main"), {"no-print": "pass"})
        self.configure(NO_PRINT, {**NO_PRINT, "name": "app-only", "target": "src/app.py"})
        self.assertTrue(self.prove()[2])
        self.assertEqual(self.statuses(base="main"), {"no-print": "pass", "app-only": "pass"})

    def test_a_change_cannot_remove_a_check(self):
        self.configure()
        self.assertEqual(self.statuses(base="main"), {"no-print": "removed"})
        self.assertIn("A change can add checks, not remove them", self.details(base="main")["no-print"])
        self.assertEqual(self.cli("check", "--base", "main")[0], 1)
        (self.root / ".claude" / "product-os-checks.json").unlink()
        self.assertEqual(self.statuses(base="main"), {"no-print": "removed"})
        self.assertEqual(self.statuses(), {}, "without --base nothing knows the check was there")

    def test_a_change_cannot_drop_or_edit_a_case(self):
        (self.root / "checks/cases/no-print/bad2").mkdir()
        (self.root / "checks/cases/no-print/bad2/app.py").write_text("print(1)\n")
        self.configure({**NO_PRINT, "bad": "checks/cases/no-print/bad2"})
        self.assertTrue(self.prove()[2], "the new case is a fine case on its own")
        self.assertIn("no longer lists the bad case checks/cases/no-print/bad",
                      self.details(base="main")["no-print"])
        self.configure(NO_PRINT)
        case = self.root / "checks/cases/no-print/bad/app.py"
        case.write_text(case.read_text().replace("prices:", "the prices:"))
        self.assertTrue(self.prove()[2], "the edited case still fails")
        self.assertIn("differs from the one at main", self.details(base="main")["no-print"])
        self.assertEqual(self.prove("no-print", base="main")[2], False)

    def test_a_change_can_rewrite_the_check_if_it_is_proven_on_the_same_cases(self):
        script = self.root / "checks" / "no_print.py"
        script.write_text(script.read_text().replace('"""Fail', '"""Rewritten. Fail'))
        self.assertEqual(self.statuses(base="main"), {"no-print": "unproven"})
        self.assertTrue(self.prove(base="main")[2])
        self.assertEqual(self.statuses(base="main", reprove=True), {"no-print": "pass"})

    def test_a_ref_without_a_project_file_sets_no_floor_and_a_bad_ref_is_exit_2(self):
        empty = self.git("commit-tree", self.git("mktree"), "-m", "Nothing")
        self.assertEqual(self.statuses(base=empty), {"no-print": "pass"})
        code, _, err = self.cli("check", "--base", "no-such-ref")
        self.assertEqual(code, 2)
        self.assertIn("git can't find the commit no-such-ref", err)

    def test_a_project_in_a_subfolder_of_the_repository(self):
        inner = self.root / "packages" / "web"
        inner.mkdir(parents=True)
        for name in (".claude", "checks", "src"):
            shutil.copytree(self.root / name, inner / name)
        self.commit("Add a second project")
        self.git("checkout", "-q", "-b", "inner-change")
        (inner / ".claude" / "product-os-checks.json").write_text('{"checks": []}')
        statuses = {r.check: r.status for r in project.check_project(inner, self.env, base="change", run_listed=True)[0]}
        self.assertEqual(statuses, {"no-print": "removed"})


class PluginFolderTest(unittest.TestCase):
    """A session that changed into the plugin's own folder to run product-os check would check the
    plugin, so a working folder there is refused unless the project is named."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.plugin, self.proj = self.root / "plugin", self.root / "proj"
        (self.plugin / ".claude-plugin").mkdir(parents=True)
        (self.plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "product-os"}', encoding="utf-8")
        (self.plugin / "tools").mkdir()
        (self.proj / ".claude").mkdir(parents=True)
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def test_the_plugin_folder_is_the_one_named_product_os(self):
        (self.root / "other" / ".claude-plugin").mkdir(parents=True)
        (self.root / "other" / ".claude-plugin" / "plugin.json").write_text('{"name": "another"}', encoding="utf-8")
        self.assertEqual(project._plugin_root(self.plugin), self.plugin)
        self.assertIsNone(project._plugin_root(self.root / "other"))
        self.assertIsNone(project._plugin_root(self.proj))

    def test_inside_the_plugin_with_nothing_named_it_refuses_naming_the_folder_before_it(self):
        os.chdir(self.plugin / "tools")
        os.environ["OLDPWD"] = str(self.proj)
        with self.assertRaises(project.ConfigError) as caught:
            project.start_folder(None, self.plugin)
        self.assertTrue(str(caught.exception).startswith("REFUSED:"))
        self.assertIn(f"Run it again with --project {self.proj}", str(caught.exception))

    def test_with_no_folder_before_it_the_refusal_says_where_to_run_it(self):
        """Through the product-os command, macOS's /bin/sh has dropped OLDPWD, so the folder an
        agent cd'd from is unknown. The line still says to run it where the session works."""
        os.chdir(self.plugin / "tools")
        os.environ.pop("OLDPWD", None)
        with self.assertRaises(project.ConfigError) as caught:
            project.start_folder(None, self.plugin)
        self.assertIn("Run it again in the folder the session works in, with no cd first",
                      str(caught.exception))
        self.assertNotIn("\n", str(caught.exception))

    def test_project_naming_the_plugin_itself_is_refused(self):
        os.chdir(self.proj)
        with self.assertRaises(project.ConfigError) as caught:
            project.start_folder(str(self.plugin), self.plugin)
        self.assertTrue(str(caught.exception).startswith("REFUSED: --project "))
        self.assertIn(f"Run it again with --project {self.proj}", str(caught.exception))

    def test_a_project_inside_the_plugin_with_its_own_claude_folder_is_a_project(self):
        example = self.plugin / "examples" / "project"
        (example / ".claude").mkdir(parents=True)
        self.assertEqual(project.start_folder(str(example), self.plugin), example)

    def test_inside_the_plugin_the_named_project_is_read(self):
        os.chdir(self.plugin / "tools")
        self.assertEqual(project.start_folder(str(self.proj), self.plugin), self.proj)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.proj)
        self.assertEqual(project.start_folder(None, self.plugin), self.proj)

    def test_outside_the_plugin_the_working_folder_is_the_project(self):
        os.chdir(self.proj)
        self.assertEqual(project.start_folder(None, self.plugin), self.proj)

    def test_check_from_inside_the_real_plugin_exits_2_and_says_how_to_run_it(self):
        if project.PLUGIN is None:
            self.skipTest("this checkout has no .claude-plugin/plugin.json named product-os")
        os.chdir(project.PLUGIN / "tools")
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = main(["check"])
        self.assertEqual(code, 2)
        self.assertIn("REFUSED:", err.getvalue())
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = main(["check", "--project", str(project.PLUGIN)])
        self.assertEqual(code, 2)
        self.assertIn("REFUSED: --project ", err.getvalue())


if __name__ == "__main__":
    unittest.main()
