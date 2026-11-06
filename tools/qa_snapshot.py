"""qa_snapshot.py - prove a QA agent changed nothing it could have used to pass.

WHY. check-page hands a fresh QA agent a built copy of the commit under test and asks it to judge
that build. The agent needs a shell to serve and measure, so its tool list can't stop it writing, and
Claude Code hooks don't run on every machine. What a shell write could change to get a pass is
known, though: the build it judges, the git folder the push check lives in, the project checkout, and
the files that say which checks and commands this machine accepted. So the caller records all of them
before the agent starts and compares them after it answers. Any difference means the QA run didn't
count.

  python qa_snapshot.py record <worktree> <sha> --out <file> [--project <dir>]
      Record, and print one line: the record's digest. Keep that line where the agent can't reach
      it, such as your own conversation: compare takes it back with --expect, so a changed record
      file is caught too. Exit 0, or 2 when the worktree isn't at <sha>.
  python qa_snapshot.py compare <file> --expect <digest>
      Exit 0 when nothing changed, 1 with one line per change, 2 when it couldn't compare.
  python qa_snapshot.py selftest
      Plants one change of each kind on a fresh repository and checks each is caught, and that an
      unchanged run passes.

WHAT IT RECORDS
  worktree   HEAD (must be <sha>), and every file under it with its sha256, the build output and
             untracked files included. A link is recorded by its target and not followed, so a
             linked node_modules isn't read.
  git        the shared git folder: every ref (the stash too), its config file, the worktree's own
             config, and every file in its hooks folder, by hash. Nothing from them is printed.
  project    the project checkout's HEAD and `git status --porcelain` (untracked files included).
  accepted   the product-os files in ~/.claude and $CLAUDE_CONFIG_DIR that decide which checks and
             commands count on this machine.
A change lists its kind and its path, never a value.

BLIND TO. A change made and undone while the agent ran; a write outside these places, such as a
file in another temp folder; what the agent says. Edits the person or the parent session make to the
project while the agent runs show up as project changes too: don't edit the project during a QA run.
"""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile

ACCEPTED = ("product-os.json", "product-os-checks.json", "product-os-checks-accepted.json",
            "product-os-commands-accepted.json")


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: "
                           + r.stderr.decode("utf-8", "replace").strip()[-200:])
    return r.stdout


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file(path):
    try:
        with open(path, "rb") as f:
            return _sha(f.read())
    except FileNotFoundError:
        return "absent"


def _tree(root, skip=()):
    """{relative path: sha256, or 'link -> target'} for every file under root, links not followed."""
    out = {}
    for d, dirs, files in os.walk(root):
        rel_d = os.path.relpath(d, root)
        for name in list(dirs):
            p = os.path.join(d, name)
            if os.path.islink(p):
                out[os.path.normpath(os.path.join(rel_d, name))] = "link -> " + os.readlink(p)
                dirs.remove(name)
            elif os.path.normpath(os.path.join(rel_d, name)) in skip:
                dirs.remove(name)
        for name in files:
            p = os.path.join(d, name)
            rel = os.path.normpath(os.path.join(rel_d, name))
            if rel in skip:
                continue
            out[rel] = "link -> " + os.readlink(p) if os.path.islink(p) else _file(p)
    return out


def _config_dirs():
    dirs = [os.path.join(os.path.expanduser("~"), ".claude")]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(os.path.abspath(os.path.expanduser(os.environ["CLAUDE_CONFIG_DIR"])))
    return sorted(set(dirs))


def take(worktree, project):
    """Everything this tool records, as {kind: {name: value}}."""
    worktree, project = os.path.abspath(worktree), os.path.abspath(project)
    common = os.path.abspath(os.path.join(worktree, _git(worktree, "rev-parse", "--git-common-dir")
                                          .decode().strip()))
    own = os.path.abspath(os.path.join(worktree, _git(worktree, "rev-parse", "--git-dir").decode().strip()))
    git = {"refs": _sha(_git(worktree, "for-each-ref", "--format=%(refname) %(objectname)")),
           "config": _file(os.path.join(common, "config")),
           "worktree config": _file(os.path.join(own, "config.worktree"))}
    for name, value in _tree(os.path.join(common, "hooks")).items():
        git["hooks/" + name] = value
    return {
        "worktree": {"HEAD": _git(worktree, "rev-parse", "HEAD").decode().strip(),
                     **{"file " + k: v for k, v in _tree(worktree, skip=(".git",)).items()}},
        "git": git,
        "project": {"HEAD": _git(project, "rev-parse", "HEAD").decode().strip(),
                    "status": _git(project, "status", "--porcelain", "--untracked-files=all")
                    .decode("utf-8", "replace")},
        "accepted": {os.path.join(d, n): _file(os.path.join(d, n)) for d in _config_dirs() for n in ACCEPTED},
    }


def _digest(record):
    return _sha(json.dumps(record, sort_keys=True).encode("utf-8"))


def record(worktree, sha, out, project="."):
    head = _git(worktree, "rev-parse", "HEAD").decode().strip()
    want = _git(worktree, "rev-parse", sha + "^{commit}").decode().strip()
    if head != want:
        print(f"qa_snapshot: {worktree} is at {head[:12]}, not {sha}", file=sys.stderr)
        return 2
    data = {"worktree_path": os.path.abspath(worktree), "project_path": os.path.abspath(project),
            "snapshot": take(worktree, project)}
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out)
    print(f"qa_snapshot digest {_digest(data)}")
    return 0


def differences(before, after):
    out = []
    for kind in before:
        b, a = before[kind], after.get(kind, {})
        for name in sorted(set(b) | set(a)):
            if b.get(name) != a.get(name):
                what = "added" if name not in b else "removed" if name not in a else "changed"
                label = name if kind != "project" or name == "HEAD" else "uncommitted changes"
                out.append(f"{kind}: {what} {label}")
                if kind == "project" and name == "status":
                    was = set(b.get(name, "").splitlines())
                    out += [f"  {line}" for line in a.get(name, "").splitlines() if line not in was][:20]
    return out


def compare(path, expect):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"qa_snapshot: can't read {path}: {e}", file=sys.stderr)
        return 2
    if _digest(data) != expect:
        print(f"record: changed {path} (its digest isn't the one record printed)")
        return 1
    try:
        now = take(data["worktree_path"], data["project_path"])
    except (RuntimeError, OSError, KeyError) as e:
        print(f"qa_snapshot: couldn't take the snapshot again: {e}", file=sys.stderr)
        return 2
    diff = differences(data["snapshot"], now)
    for line in diff:
        print(line)
    if not diff:
        print("qa_snapshot: nothing changed")
    return 1 if diff else 0


def selftest():
    results = []

    def check(name, ok):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    def sh(cwd, *args):
        subprocess.run(args, cwd=cwd, check=True, capture_output=True, timeout=120)

    def fixture(root):
        project, home = os.path.join(root, "project"), os.path.join(root, "home")
        os.makedirs(os.path.join(project, "src"))
        os.makedirs(os.path.join(home, ".claude"))
        with open(os.path.join(home, ".claude", "product-os-checks-accepted.json"), "w") as f:
            f.write('{"projects": {}}\n')
        with open(os.path.join(project, "src", "page.html"), "w") as f:
            f.write("<h1>Hi</h1>\n")
        with open(os.path.join(project, ".gitignore"), "w") as f:
            f.write("dist/\n")
        g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
        sh(project, "git", "init", "-q")
        sh(project, "git", "add", ".")
        sh(project, *g, "commit", "-qm", "one")
        sha = _git(project, "rev-parse", "HEAD").decode().strip()
        wt = os.path.join(root, "check-wt")
        sh(project, "git", "worktree", "add", "-q", "--detach", wt, sha)
        os.makedirs(os.path.join(wt, "dist"))
        with open(os.path.join(wt, "dist", "index.html"), "w") as f:
            f.write("<h1>Hi</h1>\n")
        os.symlink(os.path.join(root, "elsewhere"), os.path.join(wt, "node_modules"))
        return project, wt, sha, home, g

    def write(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(text)

    plants = {
        "an edit to a tracked file in the worktree": ("worktree", lambda p, w, g: write(os.path.join(w, "src", "page.html"), "x")),
        "an edit to the build it judges": ("worktree", lambda p, w, g: write(os.path.join(w, "dist", "index.html"), "x")),
        "a new file in the worktree": ("worktree", lambda p, w, g: write(os.path.join(w, "dist", "extra.css"), "x")),
        "a commit in the worktree": ("worktree", lambda p, w, g: sh(w, *g, "commit", "-q", "--allow-empty", "-m", "x")),
        "a new branch": ("git", lambda p, w, g: sh(w, "git", "branch", "qa-made")),
        "a stash": ("git", lambda p, w, g: (write(os.path.join(w, "src", "page.html"), "x"), sh(w, *g, "stash", "-q"))),
        "a git config change": ("git", lambda p, w, g: sh(w, "git", "config", "core.hooksPath", "/dev/null")),
        "a file in the hooks folder": ("git", lambda p, w, g: write(os.path.join(p, ".git", "hooks", "pre-push"), "exit 0\n")),
        "an edit in the project checkout": ("project", lambda p, w, g: write(os.path.join(p, "src", "page.html"), "x")),
        "an accepted-checks file change": ("accepted", lambda p, w, g: write(os.path.join(os.path.expanduser("~"), ".claude",
                                                                             "product-os-checks-accepted.json"), " ")),
        "a relinked node_modules": ("worktree", lambda p, w, g: (os.remove(os.path.join(w, "node_modules")),
                                                    os.symlink("/", os.path.join(w, "node_modules")))),
    }
    homes = ("HOME", "USERPROFILE")  # ~ is HOME on POSIX and USERPROFILE on Windows (kit_config.HOME_VARS)
    old_home, old_cfg = {k: os.environ.get(k) for k in homes}, os.environ.pop("CLAUDE_CONFIG_DIR", None)
    try:
        cases = [("nothing changed", None, None)] + [(n, k, f) for n, (k, f) in plants.items()]
        for name, kind, plant in cases + [("a changed record", "record", "record")]:
            with tempfile.TemporaryDirectory() as root:
                project, wt, sha, home, g = fixture(root)
                os.environ.update(dict.fromkeys(homes, home))
                out = os.path.join(root, "snap.json")
                said = io.StringIO()
                with contextlib.redirect_stdout(said):
                    code = record(wt, sha, out, project)
                expect = said.getvalue().split()[-1]
                if plant == "record":
                    with open(out, "r+", encoding="utf-8") as f:
                        data = json.load(f)
                        data["snapshot"]["worktree"]["file dist/index.html"] = "0" * 64
                        f.seek(0), f.truncate(), json.dump(data, f)
                elif plant:
                    plant(project, wt, g)
                told = io.StringIO()
                with contextlib.redirect_stdout(told), contextlib.redirect_stderr(io.StringIO()):
                    got = compare(out, expect)
                want = 0 if plant is None else 1
                named = plant is None or any(l.startswith(kind + ":") for l in told.getvalue().splitlines())
                check(f"{name}: compare exits {want}" + (f", reported under {kind}" if kind else ""),
                      code == 0 and got == want and named)
        with tempfile.TemporaryDirectory() as root:
            project, wt, sha, home, g = fixture(root)
            os.environ.update(dict.fromkeys(homes, home))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = record(wt, sha, os.path.join(root, "s.json"), project)
            sh(wt, *g, "commit", "-q", "--allow-empty", "-m", "moved")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                moved = record(wt, sha, os.path.join(root, "s2.json"), project)
            check("record refuses a worktree that isn't at the commit under test", code == 0 and moved == 2)
    finally:
        for k, v in old_home.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if old_cfg is not None:
            os.environ["CLAUDE_CONFIG_DIR"] = old_cfg
    print(f"qa_snapshot selftest: {sum(results)} of {len(results)} PASS")
    return 0 if all(results) else 1


def main(argv):
    if argv[:1] == ["selftest"]:
        return selftest()
    if argv[:1] in (["-h"], ["--help"]) or not argv:
        print(__doc__)
        return 0 if argv else 2

    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    try:
        if argv[0] == "record" and len(argv) >= 3 and opt("--out"):
            return record(argv[1], argv[2], opt("--out"), opt("--project", "."))
        if argv[0] == "compare" and len(argv) >= 2 and opt("--expect"):
            return compare(argv[1], opt("--expect"))
    except RuntimeError as e:
        print(f"qa_snapshot: {e}", file=sys.stderr)
        return 2
    print("qa_snapshot: see --help for the commands", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
