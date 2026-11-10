"""make_zip.py - build the zip a person installs Product OS from, the same bytes every time.

    python scripts/make_zip.py [REF] [--out DIR]     REF is a tag or commit; HEAD by default

WHAT IT BUILDS. dist/product-os-<version>.zip (or DIR/...): the files git tracks at REF, under one
folder, product-os-<version>/, read from git rather than the working tree, so an uncommitted edit
never ships. Unzipped, the folder is the plugin: start Claude Code with --plugin-dir on it, point
CLAUDE_CODE_PLUGIN_DIRS at it, or follow INSTALL.md from it.

NOTHING IN IT POINTS AT THE REPO. A person installing from the zip may get it from a colleague and
never see the repo, so the zip leaves out what serves only the repo (LEFT_OUT: its CI and tests,
the evals, the maintainer's scripts, the marketplace entry, and the two CI templates, which install
from the repo). In each Markdown file it also drops the repo's own text and shows the zip's:
  <!-- github-only -->     dropped in the zip, both marker lines with it
  ...
  <!-- /github-only -->
  <!-- zip-only: the zip shows this instead; skip it here
  ...                     a comment in the repo; in the zip, its text without the two marker lines
  -->
The opening line may carry a note after "zip-only", as above (ZIP_NOTE), so an agent that reads the
repo's raw text knows to skip it.
for_repo() is the same file as an agent reads it in the repo, every zip-only block dropped:
.github/run_install_doc.py runs INSTALL.md's commands through it. Then every text file the zip
would hold is scanned for a pointer at the repo (POINTERS: its URL, its owner/name, a raw-file URL,
a path under .github/) and each Markdown link for a link into what the zip leaves out. ALLOW names
the few that point elsewhere. The maintainer's handle stays where it's a name: LICENSE, pyproject's
authors and the manifests' author.

THE SAME BYTES. Entries are sorted, every timestamp is 1980-01-01, and each file's mode is 0644, or
0755 where git records it executable. So one ref gives one zip on a given Python and zlib, and the
release job's zip can be checked against a local build.

IT REFUSES (exit 1) when the five version fields at REF disagree (pyproject.toml, product_os/
__init__.py, plugin.json, .claude-plugin/plugin.json, .claude-plugin/marketplace.json), when REF
is a tag vX.Y.Z whose X.Y.Z isn't that version, when a Markdown file's markers don't pair up, or
when a file it would write points at the repo, each named as path:line. Exit 2: REF isn't a
commit, or git didn't run. It prints the zip's path, its file count, what it left out, its size
and its sha256.
"""
import argparse, hashlib, json, os, posixpath, re, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPOCH = (1980, 1, 1, 0, 0, 0)

REPO = "zhyuka/product-os"
OWNER = REPO.split("/")[0]
# A folder ends in /; any other entry is one file.
LEFT_OUT = (".github/", "tests/", "evals/", "scripts/", ".claude-plugin/marketplace.json",
            "ci/github-actions.yml", "ci/azure-pipelines.yml")
GITHUB_ONLY = re.compile(r"^[ \t]*<!-- github-only -->[ \t]*\n.*?^[ \t]*<!-- /github-only -->[ \t]*\n", re.M | re.S)
ZIP_ONLY = re.compile(r"^[ \t]*<!-- zip-only(?:[: \t][^\n]*)?\n(.*?)^[ \t]*-->[ \t]*\n", re.M | re.S)
ZIP_NOTE = "<!-- zip-only: the zip shows this instead; skip it here"   # what an agent reading the repo sees
MARKERS = ("<!-- github-only -->", "<!-- /github-only -->", "<!-- zip-only")
POINTERS = [
    ("the repo's URL", re.compile(r"github\.com/" + re.escape(OWNER) + r"(?![\w-])", re.I)),
    ("the repo's name", re.compile(r"(?<![\w.-])" + re.escape(REPO) + r"(?![\w-])", re.I)),
    ("a raw-file URL", re.compile(r"raw\.githubusercontent\.com/" + re.escape(OWNER) + r"(?![\w-])", re.I)),
    ("the repo's marketplace", re.compile(r"marketplace\W{1,3}" + re.escape(OWNER) + r"(?![\w-])|(?<![\w-])"
                                          + re.escape(OWNER) + r"\W{1,3}marketplace", re.I)),
    ("a path in the repo's CI", re.compile(r"(?<![\w-])\.github/")),
]
# (path, what) a pointer may be: each points somewhere other than this repo.
ALLOW = {
    ("skills/setup-kit/references/find-commands.md", "a path in the repo's CI"),  # the person's own project's CI
}
LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)\s#]+)")


def git(*args, binary=False):
    out = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True).stdout
    return out if binary else out.decode("utf-8")


def versions(ref):
    """Each version field at ref, by file."""
    def show(path):
        return git("show", f"{ref}:{path}")
    found = {
        "pyproject.toml": re.search(r'(?m)^version = "([^"]+)"', show("pyproject.toml")),
        "product_os/__init__.py": re.search(r'(?m)^__version__ = "([^"]+)"', show("product_os/__init__.py")),
    }
    found = {k: m.group(1) if m else None for k, m in found.items()}
    for path in ("plugin.json", ".claude-plugin/plugin.json"):
        found[path] = json.loads(show(path)).get("version")
    plugins = json.loads(show(".claude-plugin/marketplace.json")).get("plugins", [])
    found[".claude-plugin/marketplace.json"] = next(
        (p.get("version") for p in plugins if p.get("name") == "product-os"), None)
    return found


def tracked(ref):
    """(path, executable, blob id) for every file at ref, sorted by path."""
    out = []
    for entry in git("ls-tree", "-r", "-z", "--full-tree", ref).split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        mode, kind, blob = meta.split()
        if kind != "blob":
            raise SystemExit(f"refused: {path} at {ref} is a {kind}, not a file")
        if mode == "120000":
            raise SystemExit(f"refused: {path} at {ref} is a symlink, which a zip doesn't carry the same way everywhere")
        out.append((path, mode == "100755", blob))
    return sorted(out)


def left_out(path):
    """Whether the zip leaves this path out."""
    return any(path.startswith(p) if p.endswith("/") else path == p for p in LEFT_OUT)


def for_zip(text):
    """A Markdown file's text as the zip carries it: each github-only block dropped, each zip-only block shown."""
    return ZIP_ONLY.sub(lambda m: m.group(1), GITHUB_ONLY.sub("", text))


def for_scan(text):
    """for_zip's text on the repo file's lines: each line the zip drops left blank, so a finding names the line
    to edit."""
    text = GITHUB_ONLY.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return ZIP_ONLY.sub(lambda m: "\n" + m.group(1) + "\n", text)


def for_repo(text):
    """A Markdown file's text as an agent follows it in the repo: each zip-only block dropped."""
    return ZIP_ONLY.sub("", text)


def unpaired(text):
    """Why a file's markers don't pair up, or None: each github-only opened and closed, each zip-only
    closed, and none left once for_zip has run."""
    if text.count(MARKERS[0]) != text.count(MARKERS[1]):
        return f"{text.count(MARKERS[0])} {MARKERS[0]} but {text.count(MARKERS[1])} {MARKERS[1]}"
    fence = False
    for i, line in enumerate(text.splitlines(), 1):   # a marker inside a code block shows as text in the repo
        if line.lstrip().startswith("```"):
            fence = not fence
        elif fence and line.strip().startswith(MARKERS):
            return f"line {i}: {line.strip()} is inside a code block, so the repo shows it as text"
    left = [m for m in MARKERS if m in for_zip(text)]
    return f"{left[0]} left after the blocks were taken out: a marker isn't on a line of its own" if left else None


def pointers(name, text):
    """[(line, what, the matched text)] for the first pointer at the repo on each line of one file as the zip
    holds it."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        hits = [(what, m.group(0)) for what, rx in POINTERS for m in [rx.search(line)]
                if m and (name, what) not in ALLOW]
        if name.endswith(".md"):
            for m in LINK.finditer(line):
                target = posixpath.normpath(posixpath.join(posixpath.dirname(name), m.group(1)))
                if left_out(target) or left_out(target + "/"):
                    hits.append(("a link to what the zip leaves out", m.group(1)))
        if hits:
            out.append((i, *hits[0]))
    return out


def contents(ref):
    """[(path, executable, bytes)] the zip holds, and the paths it left out. Raises ValueError naming each
    pointer at the repo and each file whose markers don't pair up."""
    held, gone, problems = [], [], []
    for name, executable, blob in tracked(ref):
        if left_out(name):
            gone.append(name)
            continue
        data = git("cat-file", "blob", blob, binary=True)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            scanned = text
            if name.endswith(".md"):
                why = unpaired(text)
                if why:
                    problems.append(f"{name}: {why}")
                scanned, data = for_scan(text), for_zip(text).encode("utf-8")
            problems += [f"{name}:{i}: {what}: {hit}" for i, what, hit in pointers(name, scanned)]
        held.append((name, executable, data))
    if problems:
        raise ValueError(f"refused: {len(problems)} place(s) in the zip would point at the repo:\n"
                         + "\n".join("  " + p for p in problems))
    return held, gone


def build(ref, out_dir):
    """Write the zip for ref; return (path, file count, paths left out)."""
    found = versions(ref)
    if len(set(found.values())) != 1 or None in found.values():
        lines = "\n".join(f"  {k}: {v}" for k, v in found.items())
        raise ValueError(f"refused: the version fields at {ref} disagree:\n{lines}")
    version = next(iter(found.values()))
    tag = re.fullmatch(r"v(\d+\.\d+\.\d+.*)", ref)
    if tag and tag.group(1) != version:
        raise ValueError(f"refused: tag {ref} names {tag.group(1)}, but the files at it say {version}")
    top = f"product-os-{version}"
    files, gone = contents(ref)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{top}.zip")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        for name, executable, data in files:
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=EPOCH)
            info.create_system = 3  # unix, so the mode below is read
            info.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data, compresslevel=9)
    os.replace(tmp, path)
    return path, len(files), gone


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ref", nargs="?", default="HEAD", help="a tag or commit; HEAD by default")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"), help="the folder to write to; dist/ by default")
    a = ap.parse_args(argv)
    try:
        git("rev-parse", "--verify", "--quiet", f"{a.ref}^{{commit}}")
    except (subprocess.CalledProcessError, OSError):
        print(f"could not run: {a.ref} isn't a commit in {ROOT}")
        return 2
    try:
        path, count, gone = build(a.ref, a.out)
    except ValueError as e:
        print(e)
        return 1
    except SystemExit as e:
        print(e)
        return 1
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(f"{path}: {count} files, {os.path.getsize(path):,} bytes, sha256 {digest}")
    print(f"left out: {len(gone)} files under {', '.join(LEFT_OUT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
