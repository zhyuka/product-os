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


if __name__ == "__main__":
    unittest.main()
