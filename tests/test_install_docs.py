"""The install wording has one copy, docs/install.md. README.md and INSTALL.md carry its block word
for word, and INSTALL.md's commands are in steps the CI runner can find."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOCK = re.compile(r"<!-- install:start -->\n(.*?)<!-- install:end -->", re.S)


def block(path):
    found = BLOCK.findall(path.read_text(encoding="utf-8"))
    return found


class InstallDocsTest(unittest.TestCase):
    def test_canonical_block_is_there_once(self):
        self.assertEqual(len(block(ROOT / "docs" / "install.md")), 1)

    def test_readme_and_install_doc_match_it(self):
        canonical = block(ROOT / "docs" / "install.md")[0]
        for name in ("README.md", "INSTALL.md"):
            with self.subTest(doc=name):
                found = block(ROOT / name)
                self.assertEqual(len(found), 1, f"{name} needs the install block once")
                self.assertEqual(found[0], canonical, f"{name} words the install block differently from docs/install.md")

    def test_install_doc_steps_hold_commands_and_end_in_doctor(self):
        sys.path.insert(0, str(ROOT / ".github"))
        try:
            import run_install_doc
        finally:
            sys.path.remove(str(ROOT / ".github"))
        steps = run_install_doc.blocks((ROOT / "INSTALL.md").read_text(encoding="utf-8"))
        self.assertEqual(sorted({s for s, _ in steps}), [1, 2, 3, 4, 6])
        step3 = [b for s, b in steps if s == 3]
        self.assertEqual(len(step3), 2, "step 3 shows the change, then makes it on the person's yes")
        self.assertTrue(step3[0].rstrip().endswith("product-os\" enable"))
        self.assertTrue(step3[1].rstrip().endswith("product-os\" enable --yes"))
        self.assertIn("product-os\" doctor", steps[-1][1])


if __name__ == "__main__":
    unittest.main()
