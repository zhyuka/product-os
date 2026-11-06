"""Every skill's and agent's frontmatter reads the same with LF and with CRLF line endings.

Claude Code reads a frontmatter value that isn't valid YAML, such as an unquoted description
holding ": ", through a fallback that quotes it, and that fallback works on LF lines only. Git
for Windows checks text out with CRLF unless .gitattributes says otherwise, so in v0.1.0 a
Windows clone loaded the ado skill with no name or description, and `claude plugin validate`
failed there. Two checks hold it, and both fail on any platform:

- git checks every text file out with LF, which `git check-attr` confirms file by file;
- no value needs the fallback.

PyYAML isn't a dependency, so values are read line by line, which is enough for the flat
frontmatter these files have. The rule is first shown to fail each value `claude plugin
validate` 2.1.318 failed with CRLF and passed with LF, and to pass the quoted forms it passed.
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
KEY = re.compile(r"([A-Za-z0-9_-]+):(?:[ \t]+(.*))?$")
INDICATORS = ",[]{}#&*!|>'\"%@`"


def loaded_files():
    """The plugin files Claude Code reads frontmatter from: each skill and each agent."""
    return sorted(ROOT.glob("skills/*/SKILL.md")) + sorted(ROOT.glob("agents/*.md"))


def value_problem(value):
    """Why YAML can't read this unquoted value as written, or None."""
    if not value or value[0] in "\"'|>":
        return None
    if value[0] in "[{":
        if value.endswith("]" if value[0] == "[" else "}"):
            return None
        return f"starts with {value[0]} but isn't one flow collection"
    if value[0] in INDICATORS or value[:2] in ("- ", "? ", ": ") or value in ("-", "?", ":"):
        return f"starts with {value[0]}, which YAML reads as syntax"
    if ": " in value or value.endswith(":"):
        return 'holds ": ", which YAML reads as a second key'
    return None


def problems(front):
    """Each frontmatter line whose value only Claude Code's LF fallback reads, with the reason."""
    found = []
    block = None  # the indent of a key whose value is a | or > block
    quote = None  # the quote a value opened and hasn't closed yet
    for line in front.replace("\r\n", "\n").split("\n"):
        if quote:
            if line.rstrip().endswith(quote):
                quote = None
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if block is not None:
            if indent > block:
                continue
            block = None
        body = line.strip()
        if body.startswith("- "):  # a list item: a value, or a key and its value
            item = body[2:].lstrip()
            value = item.split(": ", 1)[1].strip() if ": " in item else item
        else:
            m = KEY.match(body)
            value = (m.group(2) or "").strip() if m else None
            if value is None:  # a plain value's second line
                if ": " in body:
                    found.append((line, 'holds ": ", which YAML reads as a second key'))
                continue
        if value[:1] in ("|", ">"):
            block = indent
            continue
        if value[:1] in ("'", '"') and (len(value) == 1 or not value.endswith(value[0])):
            quote = value[0]
            continue
        reason = value_problem(value)
        if reason:
            found.append((line, reason))
    return found


SHIPPED_ADO = ('name: ado\ndescription: Azure DevOps work items end to end: search before creating, '
               'formalize, resolve when the code ships, reconcile the board. Use for "file a ticket", '
               '"open a bug", "close these out", "audit the backlog".')

# What claude plugin validate 2.1.318 failed with CRLF. It passed each with LF but the list
# item, which its fallback doesn't reach.
BAD = {
    "v0.1.0's ado skill": SHIPPED_ADO,
    "an agent with a colon": "name: reviewer\ndescription: end to end: search",
    "a leading bracket": "name: ado\ndescription: [a] value",
    "a leading star": "name: ado\ndescription: *a value",
    "a list item with a colon": "name: page-qa\ndescription: QA one page.\nskills:\n  - check-page: the page: now",
}

# What it passed with CRLF.
GOOD = {
    "double quotes": 'name: ado\ndescription: "end to end: search before creating"',
    "single quotes": "name: ado\ndescription: 'Use for \"file a ticket\": search first'",
    "a plain value": "name: reviewer\ndescription: Reviews a change it didn't write.\ntools: Read, Grep, Glob",
    "a list": "name: page-qa\nskills:\n  - check-page\nmaxTurns: 150",
    "a flow list": "name: reviewer\ntools: [Read, Grep]",
    "a folded value": "name: ado\ndescription: >\n  end to end: search\n  before creating\nmodel: inherit",
    "a quoted value over two lines": 'name: ado\ndescription: "end to end: search\n  before creating"\nmodel: inherit',
    "a colon with no space": "name: ado\nallowed-tools: Bash(git add:*), Read",
}


class TheRule(unittest.TestCase):
    def test_each_value_that_broke_with_crlf_is_caught(self):
        for label, front in BAD.items():
            with self.subTest(label):
                self.assertTrue(problems(front), front)
                self.assertTrue(problems(front.replace("\n", "\r\n")), front)

    def test_each_value_that_read_with_crlf_passes(self):
        for label, front in GOOD.items():
            with self.subTest(label):
                self.assertEqual(problems(front), [])
                self.assertEqual(problems(front.replace("\n", "\r\n")), [])


class TheFiles(unittest.TestCase):
    def test_the_files_are_there(self):
        names = [path.relative_to(ROOT).as_posix() for path in loaded_files()]
        self.assertIn("skills/ado/SKILL.md", names)
        self.assertIn("agents/reviewer.md", names)
        self.assertGreaterEqual(len(names), 27)

    def test_no_frontmatter_value_needs_the_lf_fallback(self):
        for path in loaded_files():
            with self.subTest(path.relative_to(ROOT).as_posix()):
                m = FRONT.match(path.read_bytes().decode("utf-8"))
                self.assertIsNotNone(m, "no frontmatter")
                self.assertEqual(problems(m.group(1)), [], "quote each value listed")

    def test_the_files_were_checked_out_with_lf(self):
        # Bytes, because Python's text mode reads CRLF as LF and hides it.
        for path in loaded_files():
            with self.subTest(path.relative_to(ROOT).as_posix()):
                self.assertFalse(b"\r" in path.read_bytes(), "CRLF line endings; .gitattributes should give it eol=lf")

    def test_git_checks_every_text_file_out_with_lf(self):
        inside = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True)
        if inside.returncode != 0 or Path(inside.stdout.strip()).resolve() != ROOT:
            self.skipTest("not a git checkout of this repository")
        files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True,
                               check=True).stdout.decode("utf-8").split("\0")
        files = [f for f in files if f and not f.startswith("examples/")]
        self.assertGreater(len(files), 100)
        out = subprocess.run(["git", "-C", str(ROOT), "check-attr", "-z", "--stdin", "text", "eol"],
                             input="\0".join(files).encode("utf-8"), capture_output=True,
                             check=True).stdout.decode("utf-8").split("\0")
        attrs = {}
        for path, name, value in zip(out[0::3], out[1::3], out[2::3]):
            attrs.setdefault(path, {})[name] = value
        self.assertEqual(sorted(attrs), sorted(files))
        wrong = [f"{path}: text={a['text']} eol={a['eol']}" for path, a in sorted(attrs.items())
                 if a["text"] not in ("auto", "set") or a["eol"] != "lf"]
        self.assertEqual(wrong, [], "each should be text=auto or text, with eol=lf")


if __name__ == "__main__":
    unittest.main()
