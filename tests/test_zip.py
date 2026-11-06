"""make_zip.py: one ref gives the same bytes twice, the zip holds exactly the files git tracks at that
ref, and the unzipped folder runs as the plugin."""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_zip.py"


def make(out, ref="HEAD"):
    p = subprocess.run([sys.executable, str(SCRIPT), ref, "--out", str(out)], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


class ZipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.first, cls.second = Path(cls.tmp.name, "a"), Path(cls.tmp.name, "b")
        cls.code, cls.out = make(cls.first)
        make(cls.second)
        version = git("show", "HEAD:pyproject.toml").split('version = "', 1)[1].split('"', 1)[0]
        cls.top = f"product-os-{version}"
        cls.zip = cls.first / f"{cls.top}.zip"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_same_bytes_twice(self):
        self.assertEqual(self.code, 0, self.out)
        self.assertEqual(self.zip.read_bytes(), (self.second / self.zip.name).read_bytes())

    def test_holds_exactly_what_git_tracks(self):
        tracked = sorted(f"{self.top}/{p}" for p in git("ls-tree", "-r", "--name-only", "HEAD").splitlines())
        with zipfile.ZipFile(self.zip) as z:
            self.assertEqual(sorted(z.namelist()), tracked)
            mode = z.getinfo(f"{self.top}/bin/product-os").external_attr >> 16
        self.assertEqual(mode & 0o777, 0o755)

    @unittest.skipIf(os.name == "nt", "the launcher is a sh script; Windows runs it from Git Bash")
    def test_unzipped_folder_runs(self):
        dest = Path(self.tmp.name, "unzipped")
        with zipfile.ZipFile(self.zip) as z:
            z.extractall(dest)
        runner = dest / self.top / "bin" / "product-os"
        runner.chmod(0o755)  # extractall drops the mode; an unzip tool keeps it
        root = subprocess.run([str(runner), "--root"], capture_output=True, text=True)
        self.assertEqual(root.stdout.strip(), str((dest / self.top).resolve()))
        listed = subprocess.run([str(runner), "--list"], capture_output=True, text=True).stdout.split()
        self.assertIn("kit_config", listed)

    def test_wrong_tag_and_disagreeing_versions_refused(self):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        with tempfile.TemporaryDirectory() as clone:
            subprocess.run(["git", "clone", "-q", "--no-local", str(ROOT), clone], check=True)
            script = Path(clone, "scripts", "make_zip.py")
            script.write_bytes(SCRIPT.read_bytes())  # it reads git at the ref, never the working tree

            def run(*args):
                p = subprocess.run([sys.executable, str(script), *args, "--out", str(Path(clone, "out"))],
                                   capture_output=True, text=True)
                return p.returncode, p.stdout

            subprocess.run(["git", "-C", clone, "tag", "v9.9.9"], check=True)
            code, out = run("v9.9.9")
            self.assertEqual(code, 1, out)
            self.assertIn("tag v9.9.9 names 9.9.9", out)

            init = Path(clone, "product_os", "__init__.py")
            init.write_text(init.read_text().replace('__version__ = "', '__version__ = "9'))
            subprocess.run(["git", "-C", clone, "commit", "-qm", "planted", "--no-verify", "--",
                            "product_os/__init__.py"], check=True, env=env)
            code, out = run()
            self.assertEqual(code, 1, out)
            self.assertIn("disagree", out)

    def test_unknown_ref_could_not_run(self):
        code, out = make(Path(self.tmp.name, "c"), ref="no-such-ref")
        self.assertEqual(code, 2, out)


if __name__ == "__main__":
    unittest.main()
