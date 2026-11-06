"""ado_rest.py decisions --from reads a tracker cache someone hands over, and refuses a stale one.

triage takes the tracker's open decisions from this command. A file pulled more than 30 minutes
ago, or one whose age can't be read, is refused with a non-zero exit, so the list did not run.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "ado_rest.py"


def item(title, state="Active", tags="decision", kind="Task"):
    return {"fields": {"System.WorkItemType": kind, "System.State": state,
                       "System.Title": title, "System.Tags": tags}}


ITEMS = {
    "101": item("Do we keep the legacy CSV export?"),
    "102": item("Who signs off the new onboarding copy?", tags="copy; Decision"),
    "103": item("Closed decision", state="Closed"),
    "104": item("Tagged decisions, not decision", tags="decisions"),
    "105": item("No tags", tags=""),
}


class DecisionsFromTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        config = self.dir / "config.json"
        config.write_text("{}\n", encoding="utf-8")
        # No user or project settings and no keychain: the command must not need an org or a token.
        self.env = {**os.environ, "HOME": str(self.dir), "USERPROFILE": str(self.dir),
                    "PRODUCT_OS_CONFIG": str(config), "PRODUCT_OS_NO_KEYCHAIN": "1"}
        for key in ("ADO_PAT", "AZURE_DEVOPS_EXT_PAT", "CLAUDE_CONFIG_DIR"):
            self.env.pop(key, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_from(self, cache, *extra):
        path = self.dir / "tracker-cache.json"
        path.write_text(cache if isinstance(cache, str) else json.dumps(cache), encoding="utf-8")
        return subprocess.run([sys.executable, str(TOOL), "decisions", "--from", str(path), *extra],
                              cwd=self.dir, env=self.env, capture_output=True, text=True, timeout=60)

    def test_a_fresh_cache_lists_the_open_items_with_the_exact_tag(self):
        done = self.run_from({"pulled": time.time() - 60, "items": ITEMS})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("2 open decision(s)", done.stdout)
        self.assertIn("#101", done.stdout)
        self.assertIn("#102", done.stdout)
        for absent in ("#103", "#104", "#105"):
            self.assertNotIn(absent, done.stdout)

    def test_a_cache_three_hours_old_is_refused(self):
        done = self.run_from({"pulled": time.time() - 3 * 3600, "items": ITEMS})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("REFUSED", done.stderr)
        self.assertIn("180 minutes ago", done.stderr)
        self.assertIn("did not run", done.stderr)
        self.assertNotIn("#101", done.stdout)

    def test_a_cache_with_no_readable_pull_time_is_refused(self):
        for pulled in (None, 0, "this morning", True):
            with self.subTest(pulled=pulled):
                cache = {"items": ITEMS} if pulled is None else {"pulled": pulled, "items": ITEMS}
                done = self.run_from(cache)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("age is unknown", done.stderr)

    def test_a_pull_time_in_the_future_is_refused(self):
        done = self.run_from({"pulled": time.time() + 3600, "items": ITEMS})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("from now", done.stderr)

    def test_an_unreadable_or_shapeless_file_is_refused(self):
        for cache in ("not json", json.dumps({"pulled": time.time(), "items": []}), "[]"):
            with self.subTest(cache=cache[:20]):
                done = self.run_from(cache)
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("REFUSED", done.stderr)

    def test_from_goes_with_decisions_only(self):
        path = self.dir / "c.json"
        path.write_text("{}", encoding="utf-8")
        done = subprocess.run([sys.executable, str(TOOL), "audit", "--from", str(path)], cwd=self.dir,
                              env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--from goes with decisions only", done.stderr)


if __name__ == "__main__":
    unittest.main()
