"""product-os enable shows one settings key's value before and after, and writes only that key, only
with --yes; product-os doctor passes only once the plugin loads from this checkout and the launcher
is on PATH, says which value wins when the environment and the settings disagree, and names each
skill line that points at something missing."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
KEY = "CLAUDE_CODE_PLUGIN_DIRS"


class Home:
    """A scratch home: a Claude Code config folder, and a bin folder on PATH without claude in it."""

    def __init__(self, tmp, link=True):
        self.config = Path(tmp, ".claude")
        self.config.mkdir()
        self.bin = Path(tmp, "bin")
        self.bin.mkdir()
        if link and os.name != "nt":
            (self.bin / "product-os").symlink_to(ROOT / "bin" / "product-os")
        self.settings = self.config / "settings.json"

    def run(self, tool, *args, environment=None, cwd=None):
        env = {k: v for k, v in os.environ.items() if k not in (KEY, "CLAUDE_PROJECT_DIR", "PRODUCT_OS_CONFIG")}
        env.update(CLAUDE_CONFIG_DIR=str(self.config), PATH=os.pathsep.join([str(self.bin), "/usr/bin", "/bin"]),
                   HOME=str(self.config.parent), USERPROFILE=str(self.config.parent))  # ~ on Windows
        if environment:
            env[KEY] = environment
        p = subprocess.run([sys.executable, str(TOOLS / f"{tool}.py"), *args], capture_output=True, text=True, env=env,
                           cwd=cwd)
        return p.returncode, p.stdout + p.stderr


class EnableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Home(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_without_yes_it_shows_before_and_after_and_writes_nothing(self):
        text = json.dumps({"model": "m", "env": {"A": "secret-looking"}})
        self.home.settings.write_text(text)
        code, out = self.home.run("enable")
        self.assertEqual(code, 0, out)
        self.assertIn("before: unset", out)
        self.assertIn(f"after:  {json.dumps(str(ROOT))}", out)
        self.assertIn("Nothing written", out)
        self.assertEqual(self.home.settings.read_text(), text)
        self.assertNotIn("secret-looking", out, "it printed another key from the settings file")

    def test_with_yes_it_sets_the_key_and_keeps_every_other(self):
        self.home.settings.write_text(json.dumps({"model": "m", "env": {"A": "1"}, "permissions": {"ask": ["x"]}}))
        code, out = self.home.run("enable", "--yes")
        self.assertEqual(code, 0, out)
        data = json.loads(self.home.settings.read_text())
        self.assertEqual(data, {"model": "m", "permissions": {"ask": ["x"]},
                                "env": {"A": "1", KEY: str(ROOT)}})
        self.assertNotIn('"model"', out, "it printed something else from the settings file")
        code, out = self.home.run("enable", "--yes")
        self.assertEqual(code, 0, out)
        self.assertIn("already names", out)

    def test_makes_the_file_when_there_is_none(self):
        self.assertEqual(self.home.run("enable", "--yes")[0], 0)
        self.assertEqual(json.loads(self.home.settings.read_text()), {"env": {KEY: str(ROOT)}})

    def test_refuses_another_value_and_a_broken_file_and_changes_neither(self):
        for text in (json.dumps({"env": {KEY: "/elsewhere"}}), "{not json", "[]", json.dumps({"env": "x"})):
            with self.subTest(settings=text):
                self.home.settings.write_text(text)
                code, out = self.home.run("enable", "--yes")
                self.assertEqual(code, 1, out)
                self.assertEqual(self.home.settings.read_text(), text)

    def test_says_when_the_environment_names_another_folder(self):
        code, out = self.home.run("enable", "--yes", environment="/elsewhere")
        self.assertEqual(code, 0, out)
        self.assertIn("That value wins over the settings key", out)


@unittest.skipIf(os.name == "nt", "the launcher is a sh script; Windows runs it from Git Bash")
class DoctorTest(unittest.TestCase):
    def test_passes_only_once_the_plugin_loads_from_here_and_the_launcher_is_on_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp)
            code, out = home.run("doctor")
            self.assertEqual(code, 1, out)
            self.assertIn("MISS plugin: Claude Code doesn't load this folder", out)
            self.assertIn("ok   runner:", out)
            home.run("enable", "--yes")
            code, out = home.run("doctor")
            self.assertEqual(code, 0, out)
            self.assertIn(f"ok   plugin: {KEY} in", out)
            self.assertIn("the plugin list didn't run", out)
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp, link=False)
            home.run("enable", "--yes")
            code, out = home.run("doctor")
            self.assertEqual(code, 1, out)
            self.assertIn("MISS runner: product-os isn't on PATH", out)

    def test_a_value_naming_another_folder_is_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp)
            home.settings.write_text(json.dumps({"env": {KEY: "/elsewhere"}}))
            code, out = home.run("doctor")
            self.assertEqual(code, 1, out)
            self.assertIn("which doesn't name", out)

    def test_names_both_values_and_says_the_environments_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp)
            home.run("enable", "--yes")
            code, out = home.run("doctor", environment="/elsewhere")
            self.assertEqual(code, 1, out)
            self.assertIn("The environment's value wins, so this checkout doesn't load", out)
            self.assertIn('"/elsewhere" in the environment', out)
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp)
            home.settings.write_text(json.dumps({"env": {KEY: "/elsewhere"}}))
            code, out = home.run("doctor", environment=str(ROOT))
            self.assertEqual(code, 0, out)
            self.assertIn("so the settings key doesn't load", out)

    def test_checks_the_projects_minimum_version_only_inside_a_project_that_sets_one(self):
        sys.path.insert(0, str(TOOLS))
        try:
            import doctor
        finally:
            sys.path.remove(str(TOOLS))
        have = doctor.version()
        major, minor, patch = doctor.version_key(have)
        with tempfile.TemporaryDirectory() as tmp:
            home = Home(tmp)
            project = Path(tmp, "project")
            (project / ".claude").mkdir(parents=True)
            home.run("enable", "--yes")
            code, out = home.run("doctor", cwd=project)
            self.assertNotIn("version:", out)
            for want, ok in ((f"{major}.{minor + 1}.0", False), (have, True), (f"{major}.{minor}", True)):
                with self.subTest(min_version=want):
                    (project / ".claude" / "product-os.json").write_text(json.dumps({"setup": {"min_version": want}}))
                    code, out = home.run("doctor", cwd=project)
                    self.assertIn(f"{'ok  ' if ok else 'MISS'} version: product-os {have}; this project needs {want}", out)
                    self.assertEqual(code, 0 if ok else 1, out)

    def test_names_each_skill_line_that_points_at_something_missing(self):
        sys.path.insert(0, str(TOOLS))
        try:
            import doctor
        finally:
            sys.path.remove(str(TOOLS))
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp, "skills", "planted")
            (skill / "scripts").mkdir(parents=True)
            (skill / "scripts" / "here.py").write_text("")
            (skill / "SKILL.md").write_text(
                "Run `product-os no_such_tool`, then `product-os kit_config` and `product-os check`.\n"
                "Run `python3 \"${CLAUDE_SKILL_DIR}/scripts/gone.py\"` and `${CLAUDE_SKILL_DIR}/scripts/here.py`.\n"
                "See [the steps](references/missing.md) and [a source](url).\n"
                "When `product-os` isn't on PATH, `product-os check` refuses. Prose: product-os checks.\n")
            Path(tmp, "tools").mkdir()
            Path(tmp, "tools", "kit_config.py").write_text("")
            old = doctor.ROOT
            doctor.ROOT = tmp
            try:
                misses = doctor.skill_misses()
            finally:
                doctor.ROOT = old
        self.assertEqual(len(misses), 3, misses)
        self.assertIn("SKILL.md:1: calls product-os no_such_tool", misses[0])
        self.assertIn("names scripts/gone.py", misses[1])
        self.assertIn("links references/missing.md", misses[2])


if __name__ == "__main__":
    unittest.main()
