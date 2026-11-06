"""A project's own checks: `product-os check` with no folder, and `product-os prove`.

A check is a command that exits 0 when what it inspects passes, and non-zero when it
doesn't. The project lists its checks in .claude/product-os-checks.json:

    {
      "checks": [
        {
          "name": "no-print",
          "run": "{python} checks/no_print.py {target}",
          "target": "src",
          "bad": "checks/cases/no-print/bad",
          "good": "checks/cases/no-print/good"
        }
      ]
    }

run is a command line, split into words as a POSIX shell splits them, or a list of words.
It runs from the project root without a shell, so a pipe or a redirect in it is just a word.
{target} becomes the path the check inspects, and {python} the Python that runs product-os.
target defaults to ".". bad and good are each a path or a list of paths, to files or
folders: the planted cases the check has to fail and the known-good cases it has to pass.
timeout is in seconds and defaults to 900.

A check counts only with a proof: a record in .claude/product-os-checks-proofs.json that it
failed each bad case and passed each good one. `product-os prove` runs the cases and
writes it. The record holds a fingerprint of the check, which covers its run, target and
case lists and every file in the project that run names, and one of each case's files, so a
change to any of them leaves the check unproven until it is proven again. On a person's own
machine a check runs only once they accepted it (see "Accepted checks" below). `check
--run-listed` runs every listed check on the project's records instead, and `check --prove`
runs the cases again instead of trusting a record. CI should pass both, since an agent can
write a record by hand.

`product-os prove --check FILE` proves checks from another file, such as checks/<name>.json,
before they are listed. Except in bypass and auto mode, Claude Code asks the user before an
agent writes in .claude/, so an agent can prove a new check first and the user approves
listing a check that has already caught its bad case. The same entry, listed unchanged, counts as proven.

A project can add checks, but it can't take one away or change one, as with the hook
settings in hooks.py:

- The user's own product-os-checks.json can list checks for a project, next to its
  qa_commands. Those always run, and a project check with the same name is left out.
- With --base REF, every check the project file had at REF has to stay. Leaving one out,
  or dropping or changing one of its cases, fails. Its command may change, but the new
  one has to be proven on the same cases. CI passes the branch a change would merge into.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__, hooks, repo

PROOFS = hooks.PROOFS
FIELDS = ("name", "run", "target", "bad", "good", "timeout")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
TIMEOUT = 900
OUTPUT_LINES = 20  # of a failing check's output, from the end
BLOCKED = ("If a check can't pass for a reason outside your change, such as a service this "
           "machine can't reach, stop and say you are blocked: name the check, give its output "
           "and say why. Don't edit the check, its cases, the files it runs, "
           f"{PROOFS.as_posix()} or {hooks.CONFIG.as_posix()} to get it to pass.")


class ConfigError(Exception):
    """The checks can't be read, or a git ref can't: exit code 2."""


@dataclass
class Check:
    name: str
    run: list  # the words, before {target} and {python} are filled in
    target: str
    bad: list
    good: list
    timeout: float
    source: str  # where it came from, for the report

    def cases(self):
        return [(path, "fail") for path in self.bad] + [(path, "pass") for path in self.good]


@dataclass
class Result:
    check: str
    status: str  # pass, fail, unproven, removed or error. Only pass passes.
    detail: str
    output: str = ""


# Reading the checks -----------------------------------------------------------

def parse(entries, where, source):
    """[Check] from a JSON list. Raises ConfigError naming the first problem."""
    if not isinstance(entries, list):
        raise ConfigError(f"{where}: \"checks\" must be a list")
    checks, seen = [], set()
    for entry in entries:
        check = _parse_one(entry, where, source)
        if check.name in seen:
            raise ConfigError(f"{where}: two checks are named {check.name!r}")
        seen.add(check.name)
        checks.append(check)
    return checks


def _parse_one(entry, where, source):
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: each check must be a JSON object")
    name = entry.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ConfigError(f"{where}: each check needs a \"name\" made of letters, digits, dots, "
                          "dashes and underscores")
    where = f"{where}, check {name!r}"
    unknown = sorted(set(entry) - set(FIELDS))
    if unknown:
        raise ConfigError(f"{where}: unknown field {unknown[0]!r}")
    run = entry.get("run")
    if isinstance(run, str):
        try:
            words = shlex.split(run)
        except ValueError as err:
            raise ConfigError(f"{where}: \"run\" can't be split into words ({err})") from None
    elif isinstance(run, list) and all(isinstance(word, str) for word in run):
        words = list(run)
    else:
        raise ConfigError(f"{where}: \"run\" must be a command line or a list of words")
    if not words:
        raise ConfigError(f"{where}: \"run\" is empty")
    if not any("{target}" in word for word in words):
        raise ConfigError(f"{where}: \"run\" has to name {{target}}, so prove can point the "
                          "check at its cases")
    target = entry.get("target", ".")
    if not isinstance(target, str) or not target:
        raise ConfigError(f"{where}: \"target\" must be a path")
    timeout = entry.get("timeout", TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError(f"{where}: \"timeout\" must be a number of seconds")
    return Check(name, words, target, _paths(entry.get("bad"), where, "bad", "fail"),
                 _paths(entry.get("good"), where, "good", "pass"), timeout, source)


def _paths(value, where, key, must):
    paths = [value] if isinstance(value, str) else value
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
        raise ConfigError(f"{where}: \"{key}\" must name at least one file or folder the check "
                          f"has to {must}")
    return list(paths)


def _plugin_root(root):
    """root when it is the Product OS plugin's folder (.claude-plugin/plugin.json named product-os), else
    None: an installed package or a copy elsewhere is never taken for it."""
    try:
        with open(root / ".claude-plugin" / "plugin.json", encoding="utf-8") as f:
            return root if json.load(f).get("name") == "product-os" else None
    except (OSError, ValueError, AttributeError):
        return None


PLUGIN = _plugin_root(Path(__file__).resolve().parent.parent)


def _plugin_not_project(folder, plugin):
    """True when folder is inside the plugin's own folder and is not a project there: no .claude folder
    at or above it, up to the plugin's root. The shipped example project has one."""
    folder, root = folder.resolve(), plugin.resolve()
    if folder != root and root not in folder.parents:
        return False
    for d in (folder, *folder.parents):
        if (d / ".claude").is_dir():
            return False
        if d == root:
            return True
    return True


def _refusal(folder, how, plugin):
    """The one line: which folder, and the exact --project to run it again with."""
    cwd, prev, root = Path.cwd().resolve(), os.environ.get("OLDPWD"), plugin.resolve()
    use = next((p for p in (cwd, Path(prev).resolve() if prev else None)
                if p and p.is_dir() and root not in (p, *p.parents)), None)
    again = f"--project {use}" if use else "--project <your project folder>"
    return f"REFUSED: {folder} {how} the Product OS plugin, not a project. Run it again with {again}"


def start_folder(explicit=None, plugin=None):
    """Where to look for the project: --project, else $CLAUDE_PROJECT_DIR, else the working folder, but
    never a folder inside the plugin's own folder that isn't a project there: a session that changed
    into the plugin, or named it as --project, would check the plugin. There it raises ConfigError,
    whose line names the --project to use, as kit_config.project_dir() refuses for the tools."""
    plugin = plugin or PLUGIN
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if plugin and _plugin_not_project(p, plugin):
            raise ConfigError(_refusal(f"--project {p}", "names a folder inside", plugin))
        return p
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(os.environ["CLAUDE_PROJECT_DIR"]).expanduser()
    cwd = Path.cwd().resolve()
    if plugin and _plugin_not_project(cwd, plugin):
        raise ConfigError(_refusal(cwd, "is inside", plugin))
    return cwd


def find_root(start):
    """The nearest folder at or above start that has .claude/product-os-checks.json, else start."""
    start = Path(start).resolve()
    for folder in (start, *start.parents):
        if (folder / hooks.CONFIG).is_file():
            return folder
    return start


def project_checks(root):
    data, problem = hooks.project_file(root)
    if problem:
        raise ConfigError(problem)
    return parse(data.get("checks", []), hooks.CONFIG.as_posix(), "project")


def file_checks(path):
    """[Check] from a file that isn't the project file: one check, a list, or {"checks": [...]}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ConfigError(f"{path} could not be read ({err})") from None
    if isinstance(data, dict):
        data = data["checks"] if "checks" in data else [data]
    return parse(data, str(path), "file")


def user_checks(root, environ):
    """(the checks the user's own file lists for this project, a note to show or "")."""
    entry, path, problem, broken = hooks.user_entry(root, environ)
    if broken:
        raise ConfigError(f"{problem}, so the checks it would require can't be known")
    return parse((entry or {}).get("checks", []), str(path), "yours"), problem


@dataclass
class Plan:
    """The checks that run, and what the floor rules found before any of them ran."""
    checks: list
    findings: list  # Result for each check the project took away or changed
    notes: list  # sentences to print before the table


def plan(root, environ=None, base=None):
    """The checks to run in root. The user's checks first, then the project's; with base, the
    checks the project file had at that git ref have to stay. Raises ConfigError."""
    environ = os.environ if environ is None else environ
    mine, note = user_checks(root, environ)
    notes = [note] if note else []
    names = {check.name: check for check in mine}
    checks = list(mine)
    for check in project_checks(root):
        if check.name not in names:
            names[check.name] = check
            checks.append(check)
        elif _definition(names[check.name], root) != _definition(check, root):
            notes.append(f"The project's check {check.name!r} differs from the one in your own "
                         f"{hooks.USER_FILE}, so yours runs")
    findings = []
    for old in base_checks(root, base) if base else []:
        now = names.get(old.name)
        if now is None:
            findings.append(Result(old.name, "removed",
                                   f"{old.source} has this check and the project's doesn't now. "
                                   "A change can add checks, not remove them"))
            continue
        if now.source == "yours":
            continue  # the user's own definition runs; the base can't weaken or replace it
        problem = _kept_cases(old, now, root, base)
        if problem:  # a changed command is fine: it is proven on the cases kept here
            findings.append(Result(old.name, "removed", problem))
            checks.remove(now)
    return Plan(checks, findings, notes)


def base_checks(root, ref):
    """The checks the project file had at a git ref. [] when it had none."""
    if not _git_ok(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"):
        raise ConfigError(f"git can't find the commit {ref}. In CI, check out the full history, "
                          "so the base branch is there")
    spec = f"{ref}:./{hooks.CONFIG.as_posix()}"  # ./ makes the path start at the project root
    if not _git_ok(root, "cat-file", "-e", spec):
        return []
    text = _git(root, "show", spec)
    where = f"{hooks.CONFIG.as_posix()} at {ref}"
    try:
        data = json.loads(text)
    except ValueError as err:
        raise ConfigError(f"{where} could not be read ({err})") from None
    return parse(data.get("checks", []) if isinstance(data, dict) else None, where, where)


def _kept_cases(old, now, root, ref):
    """Why now drops or changes one of old's cases, or ""."""
    for path, must in old.cases():
        if path not in (now.bad if must == "fail" else now.good):
            kind = "bad" if must == "fail" else "good"
            return (f"it no longer lists the {kind} case {path}, which it had at {ref}. A change can "
                    "add cases, not drop them")
        if _blobs_at(root, ref, path) != _blobs_now(root, path):
            return f"its case {path} differs from the one at {ref}. A change can add cases, not edit them"
    return ""


def _run_git(root, args):
    try:
        return subprocess.run(["git", *args], cwd=str(root), capture_output=True, check=False)
    except OSError as err:
        raise ConfigError(f"git could not run ({err}), and --base needs it") from None


def _git_ok(root, *args):
    return _run_git(root, args).returncode == 0


def _git(root, *args):
    """git's output as text. Raises ConfigError when git fails."""
    done = _run_git(root, args)
    if done.returncode:
        message = done.stderr.decode("utf-8", "replace").strip()
        last = message.splitlines()[-1].rstrip(".") if message else f"exit {done.returncode}"
        raise ConfigError(f"git {args[0]} failed ({last})")
    return done.stdout.decode("utf-8", "replace")


def _blobs_at(root, ref, path):
    """{path from the root: git blob id} for the files under path at ref. git lists paths
    from the folder it runs in, which is the project root."""
    out = _git(root, "ls-tree", "-r", "-z", ref, "--", Path(path).as_posix())
    blobs = {}
    for record in filter(None, out.split("\0")):
        meta, name = record.split("\t", 1)
        blobs[name] = meta.split()[2]
    return blobs


def _blobs_now(root, path):
    """The same for the working tree, hashed the way git add would."""
    files = [Path(os.path.relpath(p, root)).as_posix() for p in _files(Path(root) / path)]
    if not files:
        return {}
    done = subprocess.run(["git", "hash-object", "--stdin-paths"], cwd=str(root), check=False,
                          input="\n".join(files).encode("utf-8"), capture_output=True)
    if done.returncode:
        raise ConfigError(f"git hash-object failed: {done.stderr.decode('utf-8', 'replace').strip()}")
    return dict(zip(files, done.stdout.decode().split()))


# Fingerprints and proof records ----------------------------------------------

def _files(path):
    """The files at path, a file or a folder, sorted. Links are followed; .git is skipped."""
    path = Path(path)
    if path.is_file():
        return [path]
    found = []
    for folder, subfolders, names in os.walk(path):
        subfolders[:] = sorted(d for d in subfolders if d != ".git")
        found.extend(Path(folder) / name for name in sorted(names))
    return found


def _digest(paths, root, extra=b""):
    """sha256 over the files' paths from root and their bytes, with CRLF read as LF so a
    Windows checkout fingerprints the same."""
    sha = hashlib.sha256(extra)
    for path in paths:
        sha.update(Path(os.path.relpath(path, root)).as_posix().encode("utf-8") + b"\0")
        sha.update(Path(path).read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return sha.hexdigest()


def case_digest(root, path):
    """The fingerprint of one case, or "" when it doesn't exist."""
    root = Path(root).resolve()
    files = _files(root / path)
    return _digest(files, root) if files else ""


DESIGN_READS = ("states", "exercise", "drift")  # the design commands that read a baseline


def _design_command(words):
    """The index of the word design in `design <command>`, or None."""
    for i, word in enumerate(words[:-1]):
        if word == "design" and words[i + 1] in DESIGN_READS + ("import",):
            return i
    return None


def _reads_default_baseline(words):
    """Whether the words run a design command that reads the baseline in design/."""
    i = _design_command(words)
    return (i is not None and words[i + 1] in DESIGN_READS
            and not any(w == "--baseline" or w.startswith("--baseline=") for w in words))


def named_files(check, root):
    """The files in the project that the check's words name, such as checks/no_print.py, every
    file in a folder they name, such as tests/, and the baseline in design/ when a design command
    reads it by default. These define the check, so changing one leaves it unproven. A folder
    that is or holds the check's target is left out: that's what the check inspects."""
    root = Path(root).resolve()
    target = (root / check.target).resolve()
    words = [w.split("=", 1)[1] if w.startswith("--") and "=" in w else w for w in check.run]
    command = _design_command(check.run)
    if command is not None:  # the word design there is the command, not the folder
        words[command] = ""
    if _reads_default_baseline(check.run):
        words.append("design")
    found = []
    for word in words:
        if not word or "{" in word:
            continue
        try:
            path = (root / word).resolve()
        except (OSError, ValueError):
            # A word no path can hold names no file: an inline `python -c` program on Windows,
            # where Python 3.9's resolve() raises on such a name, or a NUL anywhere.
            continue
        if root not in path.parents or not path.exists():
            continue
        if path.is_dir() and (path == target or path in target.parents):
            continue
        for file in _files(path):
            file = file.resolve()
            if file.is_file() and root in file.parents and file not in found:
                found.append(file)
    return found


def _definition(check, root):
    spec = json.dumps({"run": check.run, "target": check.target, "bad": check.bad,
                       "good": check.good, "timeout": check.timeout}, sort_keys=True)
    return _digest(named_files(check, root), Path(root).resolve(), spec.encode("utf-8"))


def proofs_path(root):
    """The proof records' file in root."""
    return Path(root) / PROOFS


def read_proofs(root):
    path = proofs_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ConfigError(f"{path.name} could not be read ({err})") from None
    proofs = data.get("proofs") if isinstance(data, dict) else None
    if not isinstance(proofs, dict):
        raise ConfigError(f"{path.name} must hold {{\"proofs\": {{...}}}}")
    return proofs


def record(check, root, runs):
    """The proof record for check, from the runs of its cases: [(path, must, Run)]."""
    return {"check": _definition(check, root),
            "cases": [{"path": path, "must": must, "sha256": case_digest(root, path), "exit": run.code}
                      for path, must, run in runs],
            "proven_with": f"product-os {__version__}"}


def stale(check, root, proof, accepted=False):
    """Why the stored proof doesn't cover the check as it is now, or "". With accepted, the
    proof is the one kept when the user accepted the check."""
    done, fix = ("accepted", "accept") if accepted else ("proven", "prove")
    again = f"Run product-os {fix} {check.name}"
    if not isinstance(proof, dict):
        if accepted:
            return (f"not accepted on this machine, so it didn't run. Read its command, then run "
                    f"product-os accept {check.name}")
        return f"no proof. {again}"
    if proof.get("check") != _definition(check, root):
        return f"the check changed since it was {done}, so it didn't run. {again}"
    stored = {(c.get("path"), c.get("must")): c for c in proof.get("cases") or [] if isinstance(c, dict)}
    for path, must in check.cases():
        case = stored.get((path, must))
        if case is None:
            return f"the case {path} has no proof. {again}"
        if case.get("sha256") != case_digest(root, path):
            return f"the case {path} changed since it was {done}. {again}"
    return ""


def _write_json(path, data):
    """Write data as JSON to a temp file and move it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def write_proofs(root, updates, drop=()):
    """Write the records in updates over the stored ones, and remove those named in drop.
    Records for other checks are kept."""
    proofs = {**read_proofs(root), **updates}
    for name in drop:
        proofs.pop(name, None)
    _write_json(proofs_path(root), {"proofs": dict(sorted(proofs.items()))})


# Accepted checks ---------------------------------------------------------------
#
# A project's file can list any command as a check, and its proof records are files in the
# repo that anyone can write. So on a person's own machine a check runs only once they
# accepted it: product-os accept shows each command, proves it, and keeps the proof in
# product-os-checks-accepted.json beside their own config, keyed by the project's repository and
# its folder in it (repo.repo_key), so every worktree of one repository shares the accept and a
# separate clone needs its own. A folder outside git is keyed by its real path, the key older
# records have; those are still read. CI has no such file, and passes check --run-listed instead.

def accepted_path(root, environ):
    """(the user's accepted-checks file, problem)."""
    folder, problem = hooks.user_config_folder(root, environ)
    return (folder / hooks.ACCEPTED_FILE if folder else None), problem


def _path_key(root):
    return Path(os.path.realpath(root)).as_posix()


def _accepted_key(root):
    return repo.repo_key(root) or _path_key(root)


def _read_accepted_file(path):
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as err:
        raise ConfigError(f"{path} could not be read ({err})") from None
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict) or not all(isinstance(v, dict) for v in projects.values()):
        raise ConfigError(f'{path} must hold {{"projects": {{folder: {{check name: proof}}}}}}')
    return projects


def read_accepted(root, environ):
    """{check name: proof record} for the checks the user accepted for root: those kept for its
    repository, over any an older record kept for its path."""
    projects = _read_accepted_file(accepted_path(root, environ)[0])
    return {**projects.get(_path_key(root), {}), **projects.get(_accepted_key(root), {})}


def write_accepted(root, environ, updates, drop=()):
    """Keep the records in updates as accepted for root, and forget those named in drop."""
    path, problem = accepted_path(root, environ)
    if path is None:
        raise ConfigError(problem or "there is no folder for your own product-os files")
    projects = _read_accepted_file(path)
    key, old = _accepted_key(root), _path_key(root)
    records = {**(projects.get(old, {}) if old != key else {}), **projects.get(key, {}), **updates}
    for name in drop:
        records.pop(name, None)
    if old != key:
        projects.pop(old, None)  # moved under the repository's key, so a drop can't leave it behind
    if records:
        projects[key] = dict(sorted(records.items()))
    else:
        projects.pop(key, None)
    _write_json(path, {"projects": dict(sorted(projects.items()))})


# Running ---------------------------------------------------------------------

@dataclass
class Run:
    code: object  # the exit code, or None when the command didn't start or timed out
    output: str
    problem: str = ""


def run_check(check, root, target):
    """Run check with {target} set to target, from root."""
    words = [w.replace("{target}", target).replace("{python}", sys.executable) for w in check.run]
    program = words[0]
    if os.sep in program or (os.altsep and os.altsep in program):
        found = str((Path(root) / program)) if not os.path.isabs(program) else program
        found = found if os.path.isfile(found) else None
    else:
        found = shutil.which(program)  # finds npm.cmd for npm on Windows
    if not found:
        return Run(None, "", f"{program} was not found")
    try:
        done = subprocess.run([found, *words[1:]], cwd=str(root), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=check.timeout)
    except subprocess.TimeoutExpired as err:
        return Run(None, _text(err.stdout), f"it timed out after {check.timeout:g} s")
    except OSError as err:
        return Run(None, "", f"it could not start ({err})")
    return Run(done.returncode, _text(done.stdout))


def _text(data):
    if not data:
        return ""
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else data


def _tail(text, lines=OUTPUT_LINES):
    return "\n".join(text.rstrip().splitlines()[-lines:])


def prove_one(check, root):
    """(ok, runs, problems). Each bad case has to make the check exit non-zero and each good
    case exit 0. A case where the check didn't start or timed out proves nothing."""
    runs, problems = [], []
    for path, must in check.cases():
        if not (Path(root) / path).exists():
            problems.append(f"the case {path} doesn't exist")
            continue
        run = run_check(check, root, path)
        runs.append((path, must, run))
        if run.code is None:
            problems.append(f"on {path} {run.problem}")
        elif must == "fail" and run.code == 0:
            problems.append(f"it passed the bad case {path}")
        elif must == "pass" and run.code != 0:
            problems.append(f"it failed the good case {path} (exit {run.code})")
    return not problems, runs, problems


def counts(runs):
    """(bad caught, bad, good passed, good)."""
    bad = [r for _, must, r in runs if must == "fail"]
    good = [r for _, must, r in runs if must == "pass"]
    return (sum(r.code not in (None, 0) for r in bad), len(bad),
            sum(r.code == 0 for r in good), len(good))


def check_project(root, environ=None, base=None, reprove=False, run_listed=False):
    """(results, notes). A check runs only when the user accepted it as it is now, so nothing
    the project lists runs unseen. With run_listed, as in CI, every listed check runs and the
    project's own proof records count. Raises ConfigError."""
    environ = os.environ if environ is None else environ
    root = Path(root).resolve()
    work = plan(root, environ, base)
    proofs = read_proofs(root) if run_listed else read_accepted(root, environ)
    results = list(work.findings)
    for check in work.checks:
        if not run_listed:
            why = stale(check, root, proofs.get(check.name), accepted=True)
            if why:  # not even its cases run
                results.append(Result(check.name, "unproven", why))
                continue
        if reprove:
            ok, runs, problems = prove_one(check, root)
            stored = stale(check, root, proofs.get(check.name))
            if not ok:
                results.append(Result(check.name, "unproven", "the proof didn't hold: " + "; ".join(problems)))
                continue
            if stored:
                results.append(Result(check.name, "unproven", f"its cases hold, but its record is stale: {stored}"))
                continue
        else:
            why = stale(check, root, proofs.get(check.name))
            if why:
                results.append(Result(check.name, "unproven", why))
                continue
        run = run_check(check, root, check.target)
        if run.code is None:
            results.append(Result(check.name, "error", run.problem, _tail(run.output)))
        elif run.code:
            results.append(Result(check.name, "fail", f"exit {run.code} on {check.target}", _tail(run.output)))
        else:
            results.append(Result(check.name, "pass", f"exit 0 on {check.target}"))
    return results, work.notes


def prove_project(root, names=(), environ=None, base=None, accept=False):
    """(rows, notes, ok): one row per check proven, [name, bad caught, good passed, result].
    Writes the records of the checks that held and drops those of the ones that didn't. With
    accept, the checks that held are also accepted on this machine, and those that didn't stop
    being accepted."""
    environ = os.environ if environ is None else environ
    root = Path(root).resolve()
    work = plan(root, environ, base)
    known = {check.name for check in work.checks} | {r.check for r in work.findings}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ConfigError(f"there is no check named {unknown[0]!r}")
    rows, ok = [], True
    for finding in work.findings:
        if not names or finding.check in names:
            rows.append([finding.check, "-", "-", f"not proven: {finding.detail}"])
            ok = False
    proved, held = _prove(root, [check for check in work.checks if not names or check.name in names],
                          environ if accept else None)
    return rows + proved, work.notes, ok and held


def commands(root, names=(), environ=None, base=None):
    """[(name, the command line it runs)] for the checks accept would run, so the user sees
    each command before accepting it."""
    work = plan(Path(root).resolve(), os.environ if environ is None else environ, base)
    return [(check.name, " ".join(w if w in ("{python}", "{target}") else shlex.quote(w)
                                  for w in check.run))
            for check in work.checks if not names or check.name in names]


def prove_file(root, path, environ=None):
    """(rows, notes, ok) for the checks in a file other than the project file. Their records
    are written as for listed checks, so the same entry counts once it is listed. A name the
    project or your own file already lists with another definition is refused, since the
    records are kept by name."""
    root = Path(root).resolve()
    work = plan(root, environ)
    listed = {check.name: check for check in work.checks}
    checks = file_checks(path)
    for check in checks:
        same = listed.get(check.name)
        if same is not None and _definition(same, root) != _definition(check, root):
            raise ConfigError(f"{path}: a different check named {check.name!r} is already listed. "
                              f"Give this one another name, or prove the listed one with "
                              f"product-os prove {check.name}")
    rows, ok = _prove(root, checks)
    return rows, work.notes, ok


def _prove(root, checks, accept_for=None):
    """(rows, ok). Writes the records of the checks that held and drops those of the ones that
    didn't. With accept_for, an environment, does the same in the user's accepted checks."""
    rows, updates, drop, ok = [], {}, [], True
    for check in checks:
        held, runs, problems = prove_one(check, root)
        caught, bad, passed, good = counts(runs)
        done = "proven and accepted" if accept_for is not None else "proven"
        rows.append([check.name, f"{caught} of {bad}", f"{passed} of {good}",
                     done if held else "not proven: " + "; ".join(problems)])
        if held:
            updates[check.name] = record(check, root, runs)
        else:
            drop.append(check.name)
            ok = False
    if updates or drop:
        write_proofs(root, updates, drop)
        if accept_for is not None:
            write_accepted(root, accept_for, updates, drop)
    return rows, ok
