"""The test runner in .github/run_tests.py runs tests in parallel with the same results as one
process, and locally skips a test that passed only while nothing it read has changed.

Each test copies the runner into a small project of its own and runs it there."""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

RUNNER = Path(__file__).resolve().parent.parent / ".github" / "run_tests.py"

TESTS = {
    "data.txt": "one\n",
    "helper.py": """
        from pathlib import Path

        HERE = Path(__file__).resolve()  # as the busiest modules do: it checks the file is there
        VALUE = 1


        def used():
            return 1


        def unused():
            return 2
        """,
    "things/a.txt": "",
    "tests/test_reads.py": """
        import os
        import unittest
        from pathlib import Path

        import helper

        ROOT = Path(__file__).resolve().parent.parent


        class ReadsTest(unittest.TestCase):
            def test_reads_a_file(self):
                self.assertTrue((ROOT / "data.txt").read_text())

            def test_lists_a_folder(self):
                self.assertTrue(os.listdir(ROOT / "things"))


        class ImportsTest(unittest.TestCase):
            def test_imports_a_module(self):
                self.assertEqual((helper.VALUE, helper.used()), (1, 1))
        """,
    "tests/test_source.py": """
        import unittest
        from pathlib import Path


        class SourceTest(unittest.TestCase):
            def test_finds_a_function_in_its_text(self):
                text = (Path(__file__).resolve().parent.parent / "helper.py").read_text()
                self.assertIn("def unused", text)
        """,
    "tests/test_spawns.py": """
        import subprocess
        import sys
        import unittest


        class SpawnsTest(unittest.TestCase):
            def test_starts_a_program(self):
                subprocess.run([sys.executable, "-c", "pass"], check=True)

            def test_starts_nothing(self):
                pass


        class SetUpSpawnsTest(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                subprocess.run([sys.executable, "-c", "pass"], check=True)

            def test_starts_nothing_itself(self):
                pass
        """,
    "tests/test_many.py": """
        import unittest


        class ManyTest(unittest.TestCase):
            pass


        for n in range(12):
            setattr(ManyTest, f"test_{n:02}", lambda self, n=n: self.assertGreaterEqual(n, 0))


        class SkipsTest(unittest.TestCase):
            @unittest.skip("not here")
            def test_skipped(self):
                pass


        class SkipsAllTest(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest("no browser here")

            def test_a(self):
                pass

            def test_b(self):
                pass

            def test_c(self):
                pass
        """,
    "flag.txt": "",
    "mid.txt": "before\n",
    "tests/test_there.py": """
        import os
        import subprocess
        import sys
        import unittest
        from pathlib import Path

        ROOT = Path(__file__).resolve().parent.parent


        class ThereTest(unittest.TestCase):
            def test_a_file_is_there(self):
                self.assertTrue((ROOT / "flag.txt").is_file())

            def test_sees_a_file_another_test_edits(self):
                self.assertTrue((ROOT / "mid.txt").read_text())


        class EditsTest(unittest.TestCase):
            def test_edits_a_file_when_asked(self):
                subprocess.run([sys.executable, "-c", "pass"], check=True)  # so it always runs
                if os.environ.get("EDIT_DURING_RUN"):
                    (ROOT / "mid.txt").write_text("after\\n")
                    (ROOT / "mid.txt").read_text()
        """,
}

ORDER = {
    "seen.txt": "one\n",
    "tests/test_order.py": """
        import os
        import unittest
        from pathlib import Path

        ROOT = Path(__file__).resolve().parent.parent


        class AaFirstTest(unittest.TestCase):
            def test_reads_seen_first(self):
                self.assertTrue((ROOT / "seen.txt").read_text())


        class BbBetweenTest(unittest.TestCase):
            def test_edits_seen_when_asked(self):
                if os.environ.get("EDIT_BETWEEN_BATCHES"):
                    (ROOT / "seen.txt").write_text("two\\n")


        class CcLastTest(unittest.TestCase):
            def test_reads_seen_last(self):
                self.assertTrue((ROOT / "seen.txt").read_text())
        """,
}

TEARDOWN = {
    "tests/test_teardown.py": """
        import unittest


        class TeardownTest(unittest.TestCase):
            @classmethod
            def tearDownClass(cls):
                raise RuntimeError("teardown broke")

            def test_passes(self):
                pass
        """,
}


class Project:
    def __init__(self, case, files=TESTS):
        temp = tempfile.TemporaryDirectory()
        case.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / ".github").mkdir()
        shutil.copy(RUNNER, self.root / ".github" / "run_tests.py")
        for name, text in files.items():
            self.write(name, text)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

    def run(self, *args, ci=False, env=None):
        env = {**{k: v for k, v in os.environ.items() if k != "CI"}, **(env or {})}
        if ci:
            env["CI"] = "true"
        if "-j" not in args:  # these tests run side by side already
            args = (*args, "-j", "2")
        done = subprocess.run([sys.executable, str(self.root / ".github" / "run_tests.py"), *args],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout + done.stderr

    def cached(self, *args, **kwargs):
        """The ids of the tests the run skipped as cached, after checking it passed."""
        code, out = self.run(*args, **kwargs)
        if code != 0:
            raise AssertionError(out)
        return {m.group(1) for m in re.finditer(r"^(\S+) \.\.\. ok \(cached\)$", out, re.M)}


READS = {"test_reads.ReadsTest.test_reads_a_file", "test_reads.ReadsTest.test_lists_a_folder",
         "test_reads.ImportsTest.test_imports_a_module"}
SOURCE = {"test_source.SourceTest.test_finds_a_function_in_its_text"}
THERE = {"test_there.ThereTest.test_a_file_is_there", "test_there.ThereTest.test_sees_a_file_another_test_edits"}
MONITORED = hasattr(sys, "monitoring")


class CacheTest(unittest.TestCase):
    def test_a_test_that_passed_is_skipped_while_nothing_it_read_changed(self):
        project = Project(self)
        self.assertEqual(project.cached("test_reads"), set())
        self.assertEqual(project.cached("test_reads"), READS)
        self.assertEqual(project.cached("test_reads", "-j", "1"), READS)

    def test_a_changed_file_runs_its_module_again(self):
        project = Project(self)
        project.cached("test_reads")
        project.write("data.txt", "two\n")
        self.assertEqual(project.cached("test_reads"), set())
        self.assertEqual(project.cached("test_reads"), READS)

    def test_a_changed_import_runs_its_module_again(self):
        project = Project(self)
        project.cached("test_reads")
        project.write("helper.py", textwrap.dedent(TESTS["helper.py"]) + "OTHER = 2\n")
        self.assertEqual(project.cached("test_reads"), set())

    @unittest.skipUnless(MONITORED, "Python 3.12 or later says which functions ran")
    def test_only_an_edit_to_code_that_ran_runs_a_module_again(self):
        project = Project(self)
        project.cached("test_reads", "test_source")
        helper = textwrap.dedent(TESTS["helper.py"])
        # A comment, a blank line and a function no test ran: test_reads stays skipped. The
        # test that reads helper.py as text runs again.
        project.write("helper.py", "# notes\n\n" + helper.replace("return 2", "return 3"))
        self.assertEqual(project.cached("test_reads", "test_source"), READS)
        self.assertEqual(project.cached("test_reads", "test_source"), READS | SOURCE)
        # The function test_imports_a_module ran
        project.write("helper.py", helper.replace("return 1", "return 0 + 1"))
        self.assertEqual(project.cached("test_reads", "test_source"), set())

    def test_a_new_file_in_a_listed_folder_runs_its_module_again(self):
        project = Project(self)
        project.cached("test_reads")
        project.write("things/b.txt", "")
        self.assertEqual(project.cached("test_reads"), set())

    def test_a_changed_test_file_runs_only_its_own_module(self):
        project = Project(self)
        project.cached("test_reads", "test_many")
        project.write("tests/test_many.py", textwrap.dedent(TESTS["tests/test_many.py"]) + "\nEXTRA = 1\n")
        self.assertEqual(project.cached("test_reads", "test_many"), READS)

    def test_a_file_a_test_only_checks_is_there_counts(self):
        project = Project(self)
        project.cached("test_there")
        self.assertEqual(project.cached("test_there"), THERE)
        (project.root / "flag.txt").unlink()
        code, out = project.run("test_there")
        self.assertEqual(code, 1, out)
        self.assertIn("test_a_file_is_there (test_there.ThereTest", out)
        self.assertNotIn("test_there.ThereTest.test_a_file_is_there ... ok (cached)", out)

    def test_an_edit_made_while_the_tests_run_runs_them_again(self):
        project = Project(self)
        project.cached("test_there")
        self.assertEqual(project.cached("test_there"), THERE)
        # The run skips both of ThereTest's tests, checked against mid.txt as it was, and
        # EditsTest changes mid.txt while it runs.
        self.assertEqual(project.cached("test_there", env={"EDIT_DURING_RUN": "1"}), THERE)
        self.assertEqual(project.cached("test_there"), set())

    def test_two_batches_that_saw_a_file_differently_run_again(self):
        project = Project(self, ORDER)
        # -j 1 runs the three classes in order, one batch each, and the middle one edits the
        # file the first one read.
        project.cached("test_order", "-j", "1", env={"EDIT_BETWEEN_BATCHES": "1"})
        self.assertEqual(project.cached("test_order", "-j", "1"), set())

    def test_a_teardown_that_failed_fails_again(self):
        project = Project(self, TEARDOWN)
        for _ in range(2):
            code, out = project.run("test_teardown")
            self.assertEqual(code, 1, out)
            self.assertIn("teardown broke", out)

    def test_a_cached_file_under_a_pycache_prefix_counts_as_its_source(self):
        spec = importlib.util.spec_from_file_location("run_tests_under_test", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        project = Project(self)
        source = str(project.root / "helper.py")
        with tempfile.TemporaryDirectory() as prefix, mock.patch.object(sys, "pycache_prefix", prefix):
            cached = importlib.util.cache_from_source(source)
            self.assertTrue(cached.startswith(prefix), cached)
            # On Windows the prefix leaves out the drive, and the runner's realpath puts it back.
            self.assertEqual(os.path.splitdrive(runner.source_of(cached))[1], os.path.splitdrive(source)[1])

    def test_a_test_that_starts_a_program_always_runs(self):
        project = Project(self)
        project.cached("test_spawns")
        self.assertEqual(project.cached("test_spawns"), {"test_spawns.SpawnsTest.test_starts_nothing"})

    def test_a_failure_is_never_skipped(self):
        project = Project(self)
        project.write("tests/test_fails.py", """
            import unittest


            class FailsTest(unittest.TestCase):
                def test_fails(self):
                    self.assertEqual(1, 2)
            """)
        for _ in range(2):
            code, out = project.run("test_fails")
            self.assertEqual(code, 1, out)
            self.assertIn("test_fails (test_fails.FailsTest", out)
            self.assertNotIn("(cached)", out)

    def test_ci_and_no_cache_run_everything(self):
        project = Project(self)
        project.cached("test_reads")
        self.assertEqual(project.cached("test_reads", ci=True), set())
        self.assertEqual(project.cached("test_reads", "--no-cache"), set())


class RunnerTest(unittest.TestCase):
    def outcomes(self, out):
        """(test, outcome) for each test line. A class's setup has its own line from Python 3.11,
        and a bare one before, so it's left out here and counted on its own."""
        return sorted(pair for pair in re.findall(r"^(\S+ \(\S+\)) \.\.\. (\w+)", out, re.M)
                      if not pair[0].startswith(("setUpClass ", "tearDownClass ", "setUpModule ")))

    def test_parallel_runs_report_what_one_process_reports(self):
        project = Project(self)
        project.write("tests/test_fails.py", """
            import unittest


            class FailsTest(unittest.TestCase):
                def test_fails(self):
                    self.assertEqual(1, 2)

                def test_errs(self):
                    raise RuntimeError("broken")

                def test_passes(self):
                    pass
            """)
        plain = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                               cwd=project.root, capture_output=True, text=True, timeout=120)
        code_1, one = project.run("--no-cache", "-j", "1")
        code_4, four = project.run("--no-cache", "-j", "4")
        self.assertEqual((plain.returncode, code_1, code_4), (1, 1, 1), one + four)
        self.assertEqual(self.outcomes(plain.stderr), self.outcomes(four))
        self.assertEqual(self.outcomes(one), self.outcomes(four))
        self.assertEqual(len(self.outcomes(four)), 26, four)
        for out in (plain.stderr, one, four):
            self.assertIn("Ran 26 tests", out)
            self.assertIn("FAILED (failures=1, errors=1, skipped=2)", out)
            self.assertIn("skipped 'not here'", out)
            self.assertEqual(out.count("skipped 'no browser here'"), 1, out)

    def test_failures_become_annotations(self):
        project = Project(self, {"tests/test_fails.py": """
            import unittest


            class FailsTest(unittest.TestCase):
                def test_fails(self):
                    for n in range(30):
                        print(f"line {n} of what the test printed")
                    self.assertEqual(1, 2, "one isn't two")
            """})
        code, out = project.run("--no-cache", env={"GITHUB_ACTIONS": "true"})
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("line 29 of what the test printed"), 1, out)
        self.assertRegex(out, r"(?m)^::error title=FAIL test_fails \(test_fails\.FailsTest[^:]*::.*one isn't two")
        # What the test printed comes after GitHub is told to stop reading commands, and before
        # it's told to start again.
        fence = re.search(r"(?m)^::stop-commands::(\w+)$", out)
        self.assertTrue(fence, out)
        self.assertLess(fence.start(), out.index("line 29 of"))
        self.assertLess(out.index("line 29 of"), out.index(f"::{fence.group(1)}::"))

    def test_each_failed_subtest_counts_as_unittest_counts_it(self):
        project = Project(self, {"tests/test_subs.py": """
            import unittest


            class SubsTest(unittest.TestCase):
                def test_three_subtests_go_wrong(self):
                    for n in range(3):
                        with self.subTest(n=n):
                            if n == 2:
                                raise RuntimeError("broken")
                            self.assertEqual(n, -1)
            """})
        plain = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                               cwd=project.root, capture_output=True, text=True, timeout=120)
        code, out = project.run("--no-cache")
        self.assertEqual((plain.returncode, code), (1, 1), out)
        self.assertIn("FAILED (failures=2, errors=1)", plain.stderr)
        self.assertIn("FAILED (failures=2, errors=1)", out)

    def test_what_a_class_setup_prints_is_shown(self):
        project = Project(self, {"tests/test_says.py": """
            import sys
            import unittest


            class SaysTest(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    print("the setup ran in these shells", file=sys.stderr)

                def test_passes(self):
                    pass
            """})
        code, out = project.run("--no-cache")
        self.assertEqual(code, 0, out)
        self.assertIn("the setup ran in these shells", out)

    def test_a_skip_after_a_failed_subtest_keeps_the_failure(self):
        project = Project(self, {"tests/test_late.py": """
            import unittest


            class LateTest(unittest.TestCase):
                def test_fails_then_skips(self):
                    with self.subTest(1):
                        self.assertEqual(1, 2)
                    self.skipTest("later")
            """})
        plain = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                               cwd=project.root, capture_output=True, text=True, timeout=120)
        code, out = project.run("--no-cache")
        self.assertEqual((plain.returncode, code), (1, 1), out)
        self.assertIn("FAILED (failures=1, skipped=1)", plain.stderr)
        self.assertIn("FAILED (failures=1, skipped=1)", out)

    def test_a_name_that_matches_no_test_runs_none(self):
        code, out = Project(self).run("no_such_test")
        self.assertEqual(code, 5, out)
        self.assertIn("NO TESTS RAN", out)

    def test_a_name_leaves_out_a_module_that_doesnt_import(self):
        project = Project(self, {**TESTS, "tests/test_broken.py": "import no_such_module\n"})
        code, out = project.run("--no-cache", "test_many.ManyTest")
        self.assertEqual(code, 0, out)
        self.assertNotIn("no_such_module", out)
        # A name for the broken module or inside it, a bare name, which may match a test of any
        # module, and a name that matches no test all show why.
        for names in (["test_broken"], ["test_broken.SomeTest.test_x"], ["NoSuchTest"], ["ManyTest"],
                      ["test_many"], ["test_many.NoSuchTest"], ["test_many", "test_broken.SomeTest.test_x"]):
            code, out = project.run("--no-cache", *names)
            self.assertEqual(code, 1, out)
            self.assertIn("No module named 'no_such_module'", out)
        self.assertRegex(out, r"(?m)^test_00 \(test_many\.ManyTest[^)]*\) \.\.\. ok")

    def test_playwrights_driver_is_known_in_a_quoted_command_line(self):
        spec = importlib.util.spec_from_file_location("run_tests_under_test", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        driver = os.path.join(os.path.abspath(os.sep), "Program Files", "py", "playwright", "driver") + os.sep
        node, sh = f"{driver}node", os.path.join(os.path.abspath(os.sep), "bin", "sh")
        line = f'"{node}" "{driver}package{os.sep}cli.js" run-driver'
        starts = [
            ("subprocess.Popen", (None, line, None, None), True),  # as Windows passes it
            ("subprocess.Popen", (node, [node, "cli.js", "run-driver"], None, None), True),
            ("os.posix_spawn", (node, [node, "cli.js"], {}), True),
            ("_posixsubprocess.fork_exec", ((os.fsencode(node),), [os.fsencode(node), b"cli.js"], None), True),
            ("_winapi.CreateProcess", (None, line, None), True),
            ("os.spawn", (0, node, [node], None), True),
            ("_winapi.CreateProcess", (sh, f'{sh} -c "{node}"', None), False),
            ("subprocess.Popen", (None, ["node", "cli.js"], driver, None), False),  # a relative program
            # The driver's path as an argument of another program isn't the driver.
            ("subprocess.Popen", (sh, [sh, "-c", f"{node} --version && touch out"], None, None), False),
            ("subprocess.Popen", (None, f'cmd.exe /c ""{node}" --version & other"', None, None), False),
            ("subprocess.Popen", (sh, [sh, "-c", "true"], driver, None), False),
            ("os.system", (f"{node} --version",), False),
        ]
        for event, args, expected in starts:
            with self.subTest(event=event, args=args):
                self.assertEqual(runner.is_driver(event, args, driver), expected)

    def test_a_module_that_doesnt_import_is_an_error(self):
        project = Project(self, {"tests/test_broken.py": "import no_such_module\n"})
        code, out = project.run()
        self.assertEqual(code, 1, out)
        self.assertIn("No module named 'no_such_module'", out)

    def test_record_writes_each_test_time(self):
        project = Project(self)
        project.run("--no-cache", "--record", "test_many")
        durations = (project.root / "tests" / "durations.json").read_text(encoding="utf-8")
        self.assertIn('"test_many.ManyTest.test_00"', durations)


if __name__ == "__main__":
    unittest.main()
