"""The live eval suite's own plumbing: the fixtures its scaffolds share.

`claude plugin eval` runs a case's scaffold in <run>/home/cwd with HOME set to <run>/home and no
CLAUDE_CONFIG_DIR, then starts the session there with CLAUDE_CONFIG_DIR set to <run>/config. These
tests plant that layout and read the result the way the session's hooks do.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from product_os import hooks

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / "evals" / "_fixtures" / "workspace.sh"
BUILDER = '{"builder_agents": ["main"], "qa_commands": ["python3 qa.py"]}'


def scaffold(cwd, home, config_dir=None):
    """Run builder_workspace in cwd with the environment plugin eval gives a scaffold."""
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "USERPROFILE": str(home), "TERM": "dumb"}
    if config_dir:
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    done = subprocess.run(["bash", "-c", f'. "{WORKSPACE}" && builder_workspace \'{BUILDER}\''],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    if done.returncode:
        raise AssertionError(f"the scaffold failed: {done.stderr}")


@unittest.skipIf(os.name == "nt", "the builder scaffolds run only where plugin eval grants a shell")
class AcceptQaCommands(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.root)]))

    def qa_commands(self, cwd, config_dir):
        config, problem = hooks.load_config(str(cwd), {"CLAUDE_CONFIG_DIR": str(config_dir)})
        self.assertEqual(problem, "")
        return config["qa_commands"]

    def test_plugin_eval_session_reads_the_accept(self):
        config, home = self.root / "config", self.root / "home"
        cwd = home / "cwd"
        config.mkdir()
        cwd.mkdir(parents=True)
        scaffold(cwd, home)
        self.assertEqual(self.qa_commands(cwd, config), ["python3 qa.py"])
        self.assertFalse((home / ".claude" / "product-os-checks.json").exists())

    def test_claude_config_dir_wins(self):
        config, other = self.root / "config", self.root / "mine"
        cwd = self.root / "home" / "cwd"
        config.mkdir()
        cwd.mkdir(parents=True)
        scaffold(cwd, self.root / "home", config_dir=other)
        self.assertEqual(self.qa_commands(cwd, other), ["python3 qa.py"])
        self.assertFalse((config / "product-os-checks.json").exists())

    def test_outside_plugin_eval_the_accept_goes_in_home(self):
        home, cwd = self.root / "home", self.root / "work" / "e-1a2b"
        cwd.mkdir(parents=True)
        home.mkdir()
        scaffold(cwd, home)
        data = json.loads((home / ".claude" / "product-os-checks.json").read_text(encoding="utf-8"))
        self.assertEqual(data, {"projects": {str(self.root / "work" / "e-*"): {"qa_commands": ["python3 qa.py"]}}})


if __name__ == "__main__":
    unittest.main()
