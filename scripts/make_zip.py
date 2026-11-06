"""make_zip.py - build the whole-plugin zip from one git ref, the same bytes every time.

    python scripts/make_zip.py [REF] [--out DIR]     REF is a tag or commit; HEAD by default

WHAT IT BUILDS. dist/product-os-<version>.zip (or DIR/...): every file git tracks at REF, under one
folder, product-os-<version>/, read from git rather than the working tree, so an uncommitted edit
never ships. Unzipped, the folder is the plugin: start Claude Code with --plugin-dir on it, point
CLAUDE_CODE_PLUGIN_DIRS at it, or follow INSTALL.md from it.

THE SAME BYTES. Entries are sorted, every timestamp is 1980-01-01, and each file's mode is 0644, or
0755 where git records it executable. So one ref gives one zip on a given Python and zlib, and the
release job's zip can be checked against a local build.

IT REFUSES (exit 1) when the five version fields at REF disagree (pyproject.toml, product_os/
__init__.py, plugin.json, .claude-plugin/plugin.json, .claude-plugin/marketplace.json), or when REF
is a tag vX.Y.Z whose X.Y.Z isn't that version. Exit 2: REF isn't a commit, or git didn't run.
It prints the zip's path, its file count, its size and its sha256.
"""
import argparse, hashlib, json, os, re, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPOCH = (1980, 1, 1, 0, 0, 0)


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


def build(ref, out_dir):
    """Write the zip for ref; return (path, file count)."""
    found = versions(ref)
    if len(set(found.values())) != 1 or None in found.values():
        lines = "\n".join(f"  {k}: {v}" for k, v in found.items())
        raise ValueError(f"refused: the version fields at {ref} disagree:\n{lines}")
    version = next(iter(found.values()))
    tag = re.fullmatch(r"v(\d+\.\d+\.\d+.*)", ref)
    if tag and tag.group(1) != version:
        raise ValueError(f"refused: tag {ref} names {tag.group(1)}, but the files at it say {version}")
    top = f"product-os-{version}"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{top}.zip")
    files = tracked(ref)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        for name, executable, blob in files:
            info = zipfile.ZipInfo(f"{top}/{name}", date_time=EPOCH)
            info.create_system = 3  # unix, so the mode below is read
            info.external_attr = ((0o100755 if executable else 0o100644) & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, git("cat-file", "blob", blob, binary=True), compresslevel=9)
    os.replace(tmp, path)
    return path, len(files)


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
        path, count = build(a.ref, a.out)
    except ValueError as e:
        print(e)
        return 1
    except SystemExit as e:
        print(e)
        return 1
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    print(f"{path}: {count} files, {os.path.getsize(path):,} bytes, sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
