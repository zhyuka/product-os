"""A tool run through a symlink imports its own siblings, not the ones beside the link.

A setup can swap one of its own tools for a symlink to this plugin's copy. A tool that finds its
folder with abspath(__file__) finds the link's folder, so `import kit_config` loads whatever
kit_config sits there. Every tool finds its folder with realpath instead.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
ABSPATH_FOLDER = re.compile(r"os\.path\.dirname\(\s*os\.path\.abspath\(\s*__file__\s*\)\s*\)")
FRONT_INSERT = re.compile(r"sys\.path\.insert\(\s*0\s*,")
# A folder put in front and taken out again a few lines on, so nothing outlasts the call.
INSERT_THEN_REMOVE = {"doctor.py", "figma_client.py", "ledger.py", "triage_lists.py"}


class SymlinkedTools(unittest.TestCase):
    def test_no_tool_finds_its_folder_with_abspath(self):
        found = [f"{p.name}:{text.count(chr(10), 0, m.start()) + 1}"
                 for p in sorted(TOOLS.glob("*.py"))
                 for text in [p.read_text(encoding="utf-8")]
                 for m in ABSPATH_FOLDER.finditer(text)]
        self.assertEqual(found, [], "these find the link's folder when run through a symlink")
        self.assertIsNotNone(ABSPATH_FOLDER.search("sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))"))

    def test_a_symlinked_tool_imports_the_plugins_kit_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live"
            live.mkdir()
            (live / "kit_config.py").write_text("raise SystemExit('the planted kit_config was imported')\n")
            try:
                os.symlink(TOOLS / "archive.py", live / "archive.py")
            except (OSError, NotImplementedError) as e:
                self.skipTest(f"no symlinks here: {e}")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            r = subprocess.run([sys.executable, str(live / "archive.py"), "--help"], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertNotIn("planted kit_config", r.stdout + r.stderr)
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            # A tool in another folder that finds its folder with abspath, linked the same way, loads
            # the planted module (the known bad); the same tool with realpath loads its own.
            plugin = Path(tmp) / "plugin"
            plugin.mkdir()
            (plugin / "kit_config.py").write_text("print('the plugin kit_config')\n")
            for way in ("abspath", "realpath"):
                (plugin / f"{way}.py").write_text(
                    f"import os, sys\nsys.path.insert(0, os.path.dirname(os.path.{way}(__file__)))\nimport kit_config\n")
                (live / f"{way}.py").symlink_to(plugin / f"{way}.py")
            runs = {way: subprocess.run([sys.executable, str(live / f"{way}.py")], cwd=tmp, env=env,
                                        capture_output=True, text=True, timeout=60)
                    for way in ("abspath", "realpath")}
            self.assertIn("planted kit_config", runs["abspath"].stdout + runs["abspath"].stderr)
            self.assertIn("the plugin kit_config", runs["realpath"].stdout)

    def test_no_tool_puts_its_folder_in_front_for_good(self):
        # Each front insert must be taken out again in the same function (the files listed above).
        found = []
        for p in sorted(TOOLS.glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for m in FRONT_INSERT.finditer(text):
                if p.name in INSERT_THEN_REMOVE and "sys.path.remove(" in text[m.end():m.end() + 1200]:
                    continue
                found.append(f"{p.name}:{text.count(chr(10), 0, m.start()) + 1}")
        self.assertEqual(found, [], "these put the plugin's folder ahead of the importer's own")

    def test_a_tool_imported_by_another_leaves_its_importers_imports_alone(self):
        # A setup's own tool imports a linked plugin tool, then a sibling both folders have. It must
        # get its own folder's copy; with the plugin's folder put in front it got the plugin's.
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live"
            live.mkdir()
            (live / "drafts_store.py").write_text("WHERE = 'the importer folder'\n")
            try:
                os.symlink(TOOLS / "ado_links.py", live / "ado_links.py")
                os.symlink(TOOLS / "kit_config.py", live / "kit_config.py")
            except (OSError, NotImplementedError) as e:
                self.skipTest(f"no symlinks here: {e}")
            (live / "importer.py").write_text(
                "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))\n"
                "import ado_links\nimport drafts_store\nprint(getattr(drafts_store, 'WHERE', drafts_store.__file__))\n")
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            r = subprocess.run([sys.executable, str(live / "importer.py")], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
            self.assertEqual(r.stdout.strip(), "the importer folder")


if __name__ == "__main__":
    unittest.main()
