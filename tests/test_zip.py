"""make_zip.py: one ref gives the same bytes twice, the zip holds the files git tracks at that ref less
what serves only the repo, nothing in it points at the repo, and the unzipped folder runs as the
plugin."""
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_zip.py"
sys.path.insert(0, str(ROOT / "scripts"))
import make_zip  # noqa: E402


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

    def test_holds_what_git_tracks_less_what_serves_only_the_repo(self):
        every = git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
        tracked = sorted(f"{self.top}/{p}" for p in every if not make_zip.left_out(p))
        with zipfile.ZipFile(self.zip) as z:
            self.assertEqual(sorted(z.namelist()), tracked)
            mode = z.getinfo(f"{self.top}/bin/product-os").external_attr >> 16
        self.assertEqual(mode & 0o777, 0o755)
        for gone in (".github/workflows/tests.yml", "tests/test_zip.py", "scripts/make_zip.py",
                     ".claude-plugin/marketplace.json", "ci/github-actions.yml"):
            self.assertIn(gone, every)
            self.assertNotIn(f"{self.top}/{gone}", tracked)
        self.assertIn(f"{self.top}/ci/pre-push", tracked)  # setup-kit copies the hooks from ci/

    def test_nothing_in_it_points_at_the_repo(self):
        # Read apart from make_zip's own patterns: the repo's address, its owner/name, a path under
        # .github/, and a marker the build should have taken out.
        found = []
        with zipfile.ZipFile(self.zip) as z:
            for name in z.namelist():
                try:
                    text = z.read(name).decode("utf-8")
                except UnicodeDecodeError:
                    continue
                rel = name.split("/", 1)[1]
                for i, line in enumerate(text.splitlines(), 1):
                    low = line.lower()
                    hit = ("github.com/zhyuka" in low or "zhyuka/product-os" in low
                           or (".github/" in line and rel != "skills/setup-kit/references/find-commands.md")
                           or (rel.endswith(".md") and ("<!-- github-only" in line or "<!-- zip-only" in line)))
                    if hit:
                        found.append(f"{rel}:{i}")
        self.assertEqual(found, [])

    def test_the_zip_text_and_the_repo_text(self):
        text = ("a\n<!-- github-only -->\nrepo only\n<!-- /github-only -->\n"
                "<!-- zip-only\nzip only\n-->\nb\n")
        self.assertEqual(make_zip.for_zip(text), "a\nzip only\nb\n")
        self.assertEqual(make_zip.for_zip(make_zip.ZIP_NOTE + "\nz\n-->\n"), "z\n")   # the note an agent reads
        self.assertEqual(make_zip.for_zip("<!-- zip-only-ish -->\n"), "<!-- zip-only-ish -->\n")
        self.assertEqual(make_zip.for_repo(text), "a\n<!-- github-only -->\nrepo only\n<!-- /github-only -->\nb\n")
        self.assertEqual(make_zip.for_scan(text).count("\n"), text.count("\n"))  # findings keep the repo's lines
        self.assertIsNone(make_zip.unpaired(text))
        self.assertIn("but 0", make_zip.unpaired("<!-- github-only -->\nx\n"))
        self.assertIn("inside a code block", make_zip.unpaired("```\n<!-- github-only -->\n```\n<!-- /github-only -->\n"))
        self.assertIn("left after", make_zip.unpaired("x <!-- zip-only\ny\n-->\n"))

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

    def test_a_pointer_at_the_repo_is_refused(self):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        with tempfile.TemporaryDirectory() as clone:
            subprocess.run(["git", "clone", "-q", "--no-local", str(ROOT), clone], check=True)
            script = Path(clone, "scripts", "make_zip.py")
            script.write_bytes(SCRIPT.read_bytes())

            def run():
                p = subprocess.run([sys.executable, str(script), "--out", str(Path(clone, "out"))],
                                   capture_output=True, text=True)
                return p.returncode, p.stdout

            self.assertEqual(run()[0], 0)
            for rel, text, why in (
                    ("docs/new.md", "Ask at https://github.com/zhyuka/product-os/issues.\n", "docs/new.md:1: the repo's URL"),
                    ("docs/new.md", "Add the `zhyuka` marketplace.\n", "docs/new.md:1: the repo's marketplace"),
                    ("docs/new.md", "See [the tests](../tests/test_zip.py).\n", "a link to what the zip leaves out"),
                    ("docs/new.md", "<!-- github-only -->\nrepo\n", "docs/new.md: 1 <!-- github-only --> but 0"),
                    ("tools/new.py", "# CI is in .github/workflows/\n", "tools/new.py:1: a path in the repo's CI")):
                with self.subTest(why=why):
                    Path(clone, rel).write_text(text, encoding="utf-8")
                    subprocess.run(["git", "-C", clone, "add", rel], check=True)
                    subprocess.run(["git", "-C", clone, "commit", "-qm", "planted", "--no-verify"], check=True, env=env)
                    code, out = run()
                    self.assertEqual(code, 1, out)
                    self.assertIn(why, out)
                    subprocess.run(["git", "-C", clone, "rm", "-q", rel], check=True)
                    subprocess.run(["git", "-C", clone, "commit", "-qm", "unplanted", "--no-verify"], check=True, env=env)
            # The same address inside a github-only block is the repo's own text, and passes.
            Path(clone, "docs/new.md").write_text(
                "<!-- github-only -->\nhttps://github.com/zhyuka/product-os\n<!-- /github-only -->\n", encoding="utf-8")
            subprocess.run(["git", "-C", clone, "add", "docs/new.md"], check=True)
            subprocess.run(["git", "-C", clone, "commit", "-qm", "wrapped", "--no-verify"], check=True, env=env)
            code, out = run()
            self.assertEqual(code, 0, out)

    def test_unknown_ref_could_not_run(self):
        code, out = make(Path(self.tmp.name, "c"), ref="no-such-ref")
        self.assertEqual(code, 2, out)


if __name__ == "__main__":
    unittest.main()
