"""kit_config.py - a project's settings for the product-os tools: its Azure DevOps org and project,
its work-item title convention, its Figma files, and what recall.py searches. Every key, for every
tool, is listed in docs/config.md.

WHY THIS EXISTS. Values like an ADO project or a Figma file key do not belong inside a tool. A tool
that carries one reads from, or files into, that project when run anywhere else. So each project
keeps its own values in a file, and no tool has a project of its own.

WHERE IT LOOKS. Two files, merged key by key, the project's over yours:
  ~/.claude/product-os.json           yours: folders on your machine (notes, transcripts), and the
                                        project to use when you work outside any project folder
  <project>/.claude/product-os.json   the project's, committed with it: the nearest one, walking up
                                        from the folder you run in, the way git finds .git
$PRODUCT_OS_CONFIG names one file to use in place of the project's (a test, or a one-off).
Either file may be a link. A link to nothing is named in a problem, never read as empty, and a
project's broken link stops the walk, so no outer file stands in for it.
A tool that needs a value neither file has stops, names the key and both places it looked, and exits
2. There is no built-in default project: a missing setting must not quietly read from or file into
somebody else's ADO project.

THE FILE. Every key is optional; a tool asks only for what it uses.
  {"ado":   {"org": "https://dev.azure.com/<org>", "project": "<project>",
             "title_prefix": "<prefix>", "search_stop": ["<word>", ...],
             "frozen_branch": "<branch>", "backlog_iteration": "<iteration name>",
             "phase_suffixes": ["design", "build", ...], "decision_tag": "decision"},
   "figma": {"files": {"<file key>": {"kind": "design", "name": "<label>"}},
             "default_file": "<file key>"},
   "seen_before": {"site": ["<path from the project root>"],
                   "notes": "<folder>", "transcripts": "<folder>"}}

  key                    read by                          what it does
  ado.org                ado.py, ado_rest.py, ado_write.py the organization URL
  ado.project            ado.py, ado_rest.py, ado_write.py the project name
  ado.title_prefix       ado.py (new, lint), ado_rest.py   titles read '<prefix> // {Page - Section} // {what}';
                         (audit title-convention)         unset, any title passes
  ado.search_stop        ado.py (search, new)             extra words the duplicate search ignores, such
                                                          as your product's name, which is in every title
  ado.frozen_branch      ado_rest.py (audit)              a branch nobody may propose merging to; the
                                                          frozen-branch-mentioned check runs only when set
  ado.backlog_iteration  ado_rest.py (audit)              the dateless "someday" iteration; done-in-backlog
                                                          runs only when set
  ado.phase_suffixes     ado_rest.py (audit dup-title)    title endings that mark a planned pair (a "Design"
                                                          and a "Build" item on one stem), not a duplicate
  ado.decision_tag       ado_rest.py (decisions)          the tag that marks an open question; default
                                                          "decision"
  figma.files            figma tools; ado.py (new)        the files a search reads when none is named; kind
                                                          is "design" or "board"
  figma.default_file     figma tools; ado.py (new)        the file a bare node id such as 123:456 refers to
  seen_before.site       recall.py                        files and folders searched as the project's own
                                                          records, e.g. a rulings file
  seen_before.notes      recall.py (fallback)             your notes folder
  seen_before.transcripts recall.py (fallback)            your meeting transcripts folder

COMMANDS. A setting that runs a command or sends a request (any key ending in _cmd, and the keys in
RUNS below) counts from the project's file only once you accept it on this machine, and again after
it changes, so cloning a repo can't choose what runs. An accept counts in every worktree of the
repository it was made in, and not in another clone. Until then it is left out of the settings, as
if unset, and need() and the listing below say so. Yours, in ~/.claude, always count.
  python kit_config.py accept <key> ...   print each named command setting and accept it here
  python kit_config.py accept --all       the same for every command setting the project's file has
The accepted ones are kept as digests in ~/.claude/product-os-commands-accepted.json.

TOKENS are never in this file. token("ADO_PAT", ...) reads the first environment variable that is set,
and otherwise, optionally, the OS keychain: on macOS the generic password with service "product-os"
and account "<the variable name>" (security add-generic-password -s product-os -a ADO_PAT -w), on
Linux `secret-tool lookup service product-os account ADO_PAT`. The value is returned, never printed.

  python kit_config.py [--project DIR]    where it looked, what each file holds, and the merged settings
  python kit_config.py --selftest         plant both files and break each rule once

The project is --project when given, else $CLAUDE_PROJECT_DIR, else the working folder, but never a
folder inside the plugin's own folder that has no .claude folder of its own (project_dir()).
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import hashlib, json, os, shutil, subprocess, sys, urllib.parse

NAME = "product-os"
FILE = os.path.join(".claude", NAME + ".json")
ENV = "PRODUCT_OS_CONFIG"
NO_KEYCHAIN = ("PRODUCT_OS_NO_KEYCHAIN",)
ACCEPTED = os.path.join(".claude", NAME + "-commands-accepted.json")
# The settings that run a command or send a request, besides any key ending in _cmd. A list of
# commands, or a list of {"name", "cmd"}, is one setting: accepting it accepts the whole list.
RUNS = {("retro", "footprint"), ("retro", "insights"), ("retro", "records"), ("retro", "loop_outcome"),
        ("retro", "measures_dir"), ("retro", "reader_proxy"), ("triage", "sources"),
        ("rebase", "surfaces"), ("scheduled_audits", "extra"), ("setup", "checks")}
MUT = set()   # selftest only: the rule each mutation breaks

_loaded = {}


class NotConfigured(RuntimeError):
    """A tool needed a setting that neither file holds."""


class InPluginFolder(NotConfigured):
    """The working folder, or --project, is inside the plugin's own folder and isn't a project there."""


def _plugin_root(here=None):
    """The plugin folder these tools sit in: the parent of tools/ when it holds .claude-plugin/plugin.json
    named product-os. None for a copy of the tools anywhere else, so a project that keeps one is never
    taken for the plugin."""
    root = os.path.dirname(here or os.path.dirname(os.path.realpath(__file__)))
    try:
        with open(os.path.join(root, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return root if json.load(f).get("name") == NAME else None
    except (OSError, ValueError, AttributeError):
        return None


PLUGIN = _plugin_root()


def _inside(path, root):
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def _plugin_not_project(folder):
    """True when folder is inside the plugin's own folder and is not a project there: no .claude folder
    at or above it, up to the plugin's root. A shipped example project has one; tools/ and the root do
    not."""
    if not PLUGIN or not _inside(folder, PLUGIN) or "no_plugin_guard" in MUT:
        return False
    d, root = os.path.realpath(folder), os.path.realpath(PLUGIN)
    while True:
        if os.path.isdir(os.path.join(d, ".claude")):
            return False
        if d == root or os.path.dirname(d) == d:
            return True
        d = os.path.dirname(d)


def _refusal(folder, how):
    """The one line: which folder, the exact --project to run it again with when the folder before a
    cd is known, and what not to do instead. Through the product-os command it isn't: macOS's /bin/sh
    drops OLDPWD as it starts. An agent refused here has gone on to read the project's file itself
    and run a command from it that wasn't accepted, so the line says not to."""
    cwd, prev = os.getcwd(), os.environ.get("OLDPWD")
    use = next((p for p in (cwd, prev) if p and os.path.isdir(p) and not _inside(p, PLUGIN)), None)
    again = (f"Run it again with --project {use}." if use else
             "Run it again in the folder the session works in, with no cd first, or with --project "
             "<that folder>.")
    return (f"REFUSED: {folder} {how} the Product OS plugin, not a project. {again} Don't read the "
            f"project's {FILE} in its place: only this tool says which of its commands may run.")


def project_dir(explicit=None):
    """The project a tool works on: explicit (the --project its caller passed), else $CLAUDE_PROJECT_DIR,
    else the working folder. Never a folder inside the plugin's own folder that isn't a project there
    (_plugin_not_project): a session that changed into the plugin, or named it as --project, would read
    the plugin as the project. There it raises InPluginFolder, whose one line names the --project to run
    it again with. $CLAUDE_PROJECT_DIR is taken as given, so the plugin's own repo can be named on
    purpose."""
    if explicit:
        p = os.path.abspath(os.path.expanduser(explicit))
        if _plugin_not_project(p):
            raise InPluginFolder(_refusal(f"--project {p}", "names a folder inside"))
        return p
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.path.abspath(os.path.expanduser(os.environ["CLAUDE_PROJECT_DIR"]))
    cwd = os.getcwd()
    if _plugin_not_project(cwd):
        raise InPluginFolder(_refusal(cwd, "is inside"))
    return cwd


def _resolve(start):
    """(folder, refusal) for a lookup: start when given, else project_dir(). Inside the plugin's own
    folder, (None, its one line)."""
    try:
        return project_dir(start), None
    except InPluginFolder as e:
        return None, str(e)


def user_path():
    return os.path.join(os.path.expanduser("~"), FILE)


def home_dir(base, *parts):
    """~/<base>/product-os/<parts>, such as home_dir(".cache", "ado")."""
    return os.path.join(os.path.expanduser("~"), base, NAME, *parts)


def project_path(start=None):
    """$PRODUCT_OS_CONFIG, else the nearest <dir>/.claude/product-os.json at or above start (by default
    project_dir(): never from inside the plugin's own folder), else None. The file in your home folder
    is yours, not a project's."""
    if os.environ.get(ENV) and "no_env" not in MUT:
        return os.path.abspath(os.path.expanduser(os.environ[ENV]))
    d = _resolve(start)[0]
    if d is None:
        return None
    mine = os.path.realpath(user_path())
    while True:
        p = os.path.join(d, FILE)
        if os.path.isfile(p) and os.path.realpath(p) != mine:
            return p
        if os.path.islink(p) and not os.path.exists(p) and "no_dangling" not in MUT:
            return p  # the project's file, linked to nothing: _read names it, and no outer file stands in
        if "no_walk" in MUT:
            return None
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def _read(path, problems):
    if not path or not os.path.exists(path):
        if path and os.path.islink(path) and "no_dangling" not in MUT:
            problems.append(f"{path} links to {os.readlink(path)}, which is missing, so its settings were left out")
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        problems.append(f"{path} could not be read: {e}")
        return {}
    if not isinstance(d, dict):
        problems.append(f"{path} holds {type(d).__name__}, not an object")
        return {}
    return d


def _merge(low, high):
    out = dict(low)
    for k, v in high.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def runs(keys):
    """True when the setting at this key path runs a command or sends a request."""
    return tuple(keys) in RUNS or (str(keys[-1]).endswith("_cmd") and "no_cmd_suffix" not in MUT)


def _commands(d, path=()):
    """(key path, value) for each command setting in d."""
    for k, v in d.items():
        p = path + (k,)
        if runs(p):
            yield p, v
        elif isinstance(v, dict):
            yield from _commands(v, p)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def accepted_path():
    return os.path.join(os.path.expanduser("~"), ACCEPTED)


def _repo_key(path):
    """"git:<the repository's git folder>:<path inside the work tree>" for a file in a git work tree,
    else None. Every worktree of one repository shares its git folder, so an accept made in one
    counts in the others; a separate clone or a fork has its own. product_os/repo.py has the same
    rule; this copy is here because the tools run without the package."""
    if "no_repo_key" in MUT:
        return None
    path = os.path.realpath(path)
    folder = os.path.dirname(path)
    try:
        top, common = (subprocess.run(["git", "-C", folder, "rev-parse", *args], capture_output=True,
                                      text=True, timeout=10) for args in
                       (["--show-toplevel"], ["--path-format=absolute", "--git-common-dir"]))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if top.returncode or common.returncode or not top.stdout.strip() or not common.stdout.strip():
        return None
    inside = os.path.relpath(path, os.path.realpath(top.stdout.strip())).replace(os.sep, "/")
    return f"git:{os.path.realpath(common.stdout.strip()).replace(os.sep, '/')}:{inside}"


def _accepted_for(projects, project):
    """The accepts kept for the project file: by its repository, over any an older record kept
    by its real path."""
    key = _repo_key(project)
    return {**projects.get(os.path.realpath(project), {}), **(projects.get(key, {}) if key else {})}


def _accepted(problems):
    """{the project file's repository key, or its real path: {dotted key: digest}} from your
    accepted-commands file."""
    d = _read(accepted_path(), problems)
    projects = d.get("projects", {})
    if not isinstance(projects, dict) or not all(isinstance(v, dict) for v in projects.values()):
        problems.append(f'{accepted_path()} must hold {{"projects": {{file: {{key: digest}}}}}}')
        return {}
    return projects


def _withhold(theirs, project, problems):
    """Take out of theirs, the project's settings, each command setting not accepted on this machine
    as it is now. [(dotted key, why)] for the ones taken out."""
    if not project:
        return []
    mine = _accepted_for(_accepted(problems), project)
    out = []
    for path, value in list(_commands(theirs)):
        key = ".".join(path)
        if mine.get(key) == _digest(value) or "no_withhold" in MUT:
            continue
        parent = theirs
        for k in path[:-1]:
            parent = parent[k]
        del parent[path[-1]]
        out.append((key, "changed since you accepted it" if key in mine else "not accepted on this machine"))
    return out


def load(start=None):
    """{"settings": merged dict, "user": path, "project": path or None, "problems": [...],
    "withheld": [(key, why)], "refused": its line or None}. Never raises: a file that will not parse is
    left out and named under problems, which need() reports. A command setting the project's file has
    and you haven't accepted is left out and named under withheld. Inside the plugin's own folder with
    no project named, no project file is read and refused says why; need() raises it."""
    d, refused = _resolve(start)
    key = (d or refused, os.environ.get(ENV), os.environ.get("CLAUDE_PROJECT_DIR"), user_path())
    if key not in _loaded:
        u, p = user_path(), project_path(d)
        problems = []
        if refused:
            problems.append(refused)
        mine, theirs = _read(u, problems), _read(p, problems)
        withheld = _withhold(theirs, p, problems)
        merged = _merge(theirs, mine) if "user_wins" in MUT else _merge(mine, theirs)
        _loaded[key] = {"settings": merged, "user": u, "project": p, "problems": problems,
                        "withheld": withheld, "refused": refused}
    return _loaded[key]


def reset():
    _loaded.clear()


# Where ~ comes from: HOME on POSIX, USERPROFILE on Windows, where Python 3.8+ ignores HOME.
HOME_VARS = ("HOME", "USERPROFILE")


def home_env(home):
    """{variable: home} for each variable ~ is read from, so a planted home folder is ~ on every platform."""
    return {k: home for k in HOME_VARS}


ISOLATED = HOME_VARS + ("CLAUDE_CONFIG_DIR", ENV, "CLAUDE_PROJECT_DIR")


def run_isolated(fn, *args):
    """fn(*args) with the person's settings out of reach, for a tool's self-test: the home folder
    (home_env) is an empty temp folder, CLAUDE_CONFIG_DIR, $PRODUCT_OS_CONFIG and $CLAUDE_PROJECT_DIR
    are unset, the working folder is another temp folder, and the loaded settings are forgotten.
    Everything is put back after, and what fn starts inherits it. A self-test that needs settings
    plants them."""
    import tempfile
    if "no_isolate" in MUT:
        return fn(*args)
    saved = {k: os.environ.get(k) for k in ISOLATED}
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="product-os-selftest-") as tmp:
        home, work = os.path.join(tmp, "home"), os.path.join(tmp, "work")
        os.makedirs(os.path.join(home, ".claude"))
        os.makedirs(work)
        for k in ISOLATED:
            os.environ.pop(k, None)
        os.environ.update(home_env(home))
        os.chdir(work)
        reset()
        try:
            return fn(*args)
        finally:
            os.chdir(cwd)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            reset()


def get(*keys, default=None, start=None):
    v = load(start)["settings"]
    for k in keys:
        if not isinstance(v, dict) or k not in v:
            return default
        v = v[k]
    return v


def need(*keys, start=None):
    """The value, or NotConfigured naming the key, both places looked, and any file that would not
    parse."""
    v = get(*keys, start=start)
    if v not in (None, "", [], {}):
        return v
    c = load(start)
    if c["refused"] and not c["project"]:
        raise InPluginFolder(c["refused"])
    dotted = ".".join(keys)
    for k, why in c["withheld"]:
        if dotted == k or dotted.startswith(k + "."):
            raise NotConfigured(f"not accepted: {k} is set in {c['project']} but {why}, so nothing "
                                f"ran. {accept_line(k)}")
    where = f"{c['project'] or 'no ' + FILE + ' at or above ' + _resolve(start)[0]}"
    msg = (f"not configured: {dotted} is not set. Looked in {where} and {c['user']}. "
           f"Set it in the project's {FILE} (see kit_config.py for the format).")
    if c["problems"]:
        msg += " " + " ".join(c["problems"])
    raise NotConfigured(msg)


def ado():
    """(org without a trailing slash, project), each None when unset."""
    org = get("ado", "org")
    return (org.rstrip("/") if isinstance(org, str) and org else None), (get("ado", "project") or None)


def ado_url(wid, org=None, project=None):
    """A work item's URL from org and project (the settings' when not given); None when either is
    unset. The ADO tools print it on each item line, so a session can hand the user the link instead
    of a bare item number."""
    if org is None and project is None:
        org, project = ado()
    if not (org and project and str(wid).isdigit()):
        return None
    return f"{org.rstrip('/')}/{urllib.parse.quote(project)}/_workitems/edit/{wid}/"


def ado_linked(text, org=None, project=None):
    """text with each line ending in the URL of every #1234 on it that the line doesn't already link,
    in the order they appear, so whichever line a session copies carries its links. Unchanged when
    org or project is unset. What counts as an id and as linked is bare_ids.unlinked's rule."""
    import bare_ids
    out = []
    for ln in str(text).split("\n"):
        urls = dict.fromkeys(ado_url(i[1:], org, project) for _, i in bare_ids.unlinked(ln) if i.startswith("#"))
        out.append(ln + "".join(f"  {u}" for u in urls if u))
    return "\n".join(out)


def figma_files():
    """{file key: (kind, name)} in the order the file lists them."""
    out = {}
    for k, v in (get("figma", "files") or {}).items():
        v = v if isinstance(v, dict) else {}
        out[k] = (v.get("kind") or "design", v.get("name") or k)
    return out


def token(*names):
    """The first of the named environment variables that is set, else the OS keychain entry for the
    first name (service NAME, account <name>), else None. Never printed, logged or written."""
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    if not names or any(os.environ.get(n) for n in NO_KEYCHAIN):
        return None
    if sys.platform == "darwin" and shutil.which("security"):
        cmd = ["security", "find-generic-password", "-s", NAME, "-a", names[0], "-w"]
    elif shutil.which("secret-tool"):
        cmd = ["secret-tool", "lookup", "service", NAME, "account", names[0]]
    else:
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def accept_line(key):
    """What follows a command setting left out until it's accepted. An agent reads this line as
    often as a person does, and it once ran the accept itself, so the line says whose step it is."""
    return (f"Accepting it is the person's step, after they read it there: product-os kit_config "
            f"accept {key}. An agent runs neither that line nor the command, and reports the part "
            f"that needs it as NOT RUN.")


def run(main):
    """Run a tool's main(); a missing setting prints its message and exits 2 instead of a traceback."""
    try:
        return main()
    except NotConfigured as e:
        print(f"{os.path.basename(sys.argv[0])}: {e}", file=sys.stderr)
        return 2


def show(start=None):
    c = load(start)
    d = _resolve(start)[0]
    print(f"user file:    {c['user']}{'' if os.path.exists(c['user']) else ' (none)'}")
    print(f"project file: {c['project'] or ('(none at or above ' + d + ')' if d else '(not looked for)')}")
    for p in c["problems"]:
        print(f"PROBLEM: {p}")
    for k, why in c["withheld"]:
        print(f"NOT ACCEPTED: {k} is set in the project file but {why}, so it is left out below and "
              f"nothing runs it. {accept_line(k)}")
    print(json.dumps(c["settings"], indent=1))
    return 0


def accept(keys, start=None):
    """Accept the project file's command settings named in keys (every one, with --all) on this
    machine: print each, and keep its digest. Exit 0, or 2 when one isn't a command setting there."""
    d, refused = _resolve(start)
    p, problems = project_path(d), []
    if refused and not p:
        print(f"kit_config: {refused}", file=sys.stderr)
        return 2
    theirs = _read(p, problems)
    if not p or problems:
        print(f"kit_config: {' '.join(problems) or 'no ' + FILE + ' at or above ' + d}", file=sys.stderr)
        return 2
    found = {".".join(k): v for k, v in _commands(theirs)}
    want = list(found) if keys == ["--all"] else keys
    missing = [k for k in want if k not in found]
    if not want or missing:
        print(f"kit_config: {', '.join(missing) or 'no key named'} is not a command setting in {p}. "
              f"Its command settings: {', '.join(found) or 'none'}", file=sys.stderr)
        return 2
    projects = _accepted(problems)
    if problems:
        print(f"kit_config: {' '.join(problems)}", file=sys.stderr)
        return 2
    key = _repo_key(p) or os.path.realpath(p)
    mine = {**_accepted_for(projects, p)}
    if key != os.path.realpath(p):
        projects.pop(os.path.realpath(p), None)  # moved under the repository's key
    projects[key] = mine
    print(f"Accepting from {p}. These run on this machine, in every worktree of its repository, "
          "until they change:")
    for k in want:
        print(f"  {k} = {json.dumps(found[k])}")
        mine[k] = _digest(found[k])
    path = accepted_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"projects": dict(sorted(projects.items()))}, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    reset()
    print(f"Kept in {path}.")
    return 0


def selftest():
    import tempfile
    here = os.path.dirname(os.path.realpath(__file__))
    base, results = [], []

    def check(name, ok, detail=""):
        base.append((name, bool(ok)))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if not ok and detail else ""))

    def write(path, d):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(d if isinstance(d, str) else json.dumps(d))

    def tool(root, cwd, code, env_extra=None):
        env = dict(os.environ, **home_env(os.path.join(root, "home")), PYTHONPATH=here,
                   PRODUCT_OS_NO_KEYCHAIN="1")
        env.pop(ENV, None)
        env.update(env_extra or {})
        for k in ("ADO_PAT", "AZURE_DEVOPS_EXT_PAT"):
            env.pop(k, None)
        return subprocess.run([sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=120)

    have_fc = os.path.exists(os.path.join(here, "figma_comments.py"))

    def checks(root):
        home, proj = os.path.join(root, "home"), os.path.join(root, "proj")
        deep, bare = os.path.join(proj, "a", "b"), os.path.join(root, "elsewhere")
        for d in (deep, bare):
            os.makedirs(d, exist_ok=True)
        old = {k: os.environ.get(k) for k in HOME_VARS}, os.environ.pop(ENV, None)
        os.environ.update(home_env(home))
        try:
            reset()
            try:
                need("ado", "org", start=bare)
                raised = ""
            except NotConfigured as e:
                raised = str(e)
            check("no file anywhere: get() is None and need() refuses, naming the key and both places",
                  get("ado", "org", start=bare) is None and "ado.org" in raised and user_path() in raised)
            write(user_path(), {"ado": {"org": "https://dev.azure.com/UserOrg/", "project": "UserProj"},
                                "seen_before": {"notes": "~/notes"}})
            write(os.path.join(proj, FILE), {"ado": {"project": "Theirs", "title_prefix": "T"},
                                             "figma": {"files": {"KEY1": {"kind": "board", "name": "B"}}}})
            reset()
            check("outside any project the user file answers",
                  get("ado", "project", start=bare) == "UserProj" and get("ado", "org", start=bare)
                  == "https://dev.azure.com/UserOrg/")
            seen = run_isolated(lambda: (get("ado", "org"), os.path.expanduser("~"), os.getcwd()))
            check("run_isolated hides the person's settings from a self-test and puts everything back",
                  seen[0] is None and seen[1] != home and os.path.expanduser("~") == home
                  and get("ado", "org", start=bare) == "https://dev.azure.com/UserOrg/", str(seen[:2]))
            check("the project file is found by walking up from a folder below it",
                  load(deep)["project"] == os.path.join(proj, FILE))
            check("the project's value wins key by key; a key only the user file has is kept",
                  get("ado", "project", start=deep) == "Theirs" and get("ado", "org", start=deep)
                  == "https://dev.azure.com/UserOrg/" and get("seen_before", "notes", start=deep) == "~/notes")
            if hasattr(os, "symlink"):
                inner = os.path.join(proj, "inner")
                os.makedirs(os.path.join(inner, ".claude"), exist_ok=True)
                os.symlink(os.path.join(root, "gone.json"), os.path.join(inner, FILE))
                reset()
                c = load(inner)
                check("a project file linked to nothing is named as a problem, and no outer file stands in",
                      c["project"] == os.path.join(inner, FILE) and get("ado", "project", start=inner) != "Theirs"
                      and any("which is missing" in p for p in c["problems"]), str(c["problems"]))
                real = user_path() + ".real"
                os.replace(user_path(), real)
                os.symlink(os.path.join(root, "gone-too.json"), user_path())
                reset()
                check("a user file linked to nothing is named as a problem",
                      any(user_path() in p and "which is missing" in p for p in load(bare)["problems"]))
                os.remove(user_path())
                os.replace(real, user_path())
                reset()
            write(os.path.join(root, "one.json"), {"ado": {"project": "Env"}})
            os.environ[ENV] = os.path.join(root, "one.json")
            reset()
            check(f"${ENV} replaces the project file", get("ado", "project", start=deep) == "Env")
            os.environ.pop(ENV)
            write(os.path.join(bare, FILE), "{not json")
            reset()
            try:
                need("ado", "title_prefix", start=bare)
                raised = ""
            except NotConfigured as e:
                raised = str(e)
            check("a file that will not parse is left out, and need() names it",
                  get("ado", "project", start=bare) == "UserProj" and "could not be read" in raised
                  and os.path.join(bare, FILE) in raised)
            os.remove(os.path.join(bare, FILE))
            check("home_dir is the product-os folder under the base",
                  home_dir(os.path.join(".local", "share"), "ledger")
                  == os.path.join(home, ".local", "share", NAME, "ledger"))

            # A command setting from a project's file counts only once accepted, as it is now.
            repo = os.path.join(root, "repo")
            write(os.path.join(repo, FILE), {"retro": {"propose_cmd": "echo theirs", "report": "r.md"},
                                             "scheduled_audits": {"extra": [["x", "x.py"]]}})
            write(user_path(), {"ado": {"org": "https://dev.azure.com/UserOrg/", "project": "UserProj"},
                                "seen_before": {"notes": "~/notes"}, "retro": {"plan_cmd": "echo mine"}})
            reset()
            try:
                need("retro", "propose_cmd", start=repo)
                raised = ""
            except NotConfigured as e:
                raised = str(e)
            check("a project's command setting is left out until accepted, and need() names the accept",
                  get("retro", "propose_cmd", start=repo) is None
                  and get("scheduled_audits", "extra", start=repo) is None
                  and "product-os kit_config accept retro.propose_cmd" in raised
                  and "An agent runs neither" in raised)
            check("the project's other settings, and your own commands, still count",
                  get("retro", "report", start=repo) == "r.md"
                  and get("retro", "plan_cmd", start=repo) == "echo mine")
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()) as said:
                code = accept(["retro.propose_cmd"], start=repo)
            check("accept prints the command it accepts, and then it counts",
                  code == 0 and "echo theirs" in said.getvalue()
                  and get("retro", "propose_cmd", start=repo) == "echo theirs"
                  and get("scheduled_audits", "extra", start=repo) is None)
            write(os.path.join(repo, FILE), {"retro": {"propose_cmd": "echo changed"}})
            reset()
            try:
                need("retro", "propose_cmd", start=repo)
                raised = ""
            except NotConfigured as e:
                raised = str(e)
            check("an accepted command that changes is left out again",
                  get("retro", "propose_cmd", start=repo) is None and "changed since" in raised)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = accept(["retro.report"], start=repo)
            check("accept refuses a key that isn't a command setting", code == 2)

            # An accept counts in every worktree of its repository, and not in another clone.
            if shutil.which("git"):
                shop = os.path.join(root, "shop")
                write(os.path.join(shop, FILE), {"retro": {"propose_cmd": "echo shop"}})
                git_env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
                for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "shop", "--no-verify"],
                             ["worktree", "add", "-q", os.path.join(root, "shop-fix")]):
                    subprocess.run(["git", "-C", shop, *args], env=git_env, capture_output=True, check=True)
                subprocess.run(["git", "clone", "-q", shop, os.path.join(root, "shop-clone")],
                               env=git_env, capture_output=True, check=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    accept(["retro.propose_cmd"], start=shop)
                reset()
                check("an accept counts in a worktree of its repository, not in a separate clone",
                      get("retro", "propose_cmd", start=os.path.join(root, "shop-fix")) == "echo shop"
                      and get("retro", "propose_cmd", start=os.path.join(root, "shop-clone")) is None)
        finally:
            for k, v in old[0].items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            if old[1] is not None:
                os.environ[ENV] = old[1]
            reset()

        o, pj = "https://dev.azure.com/Org/", "P"
        u = lambda w: f"https://dev.azure.com/Org/P/_workitems/edit/{w}/"
        check("ado_linked ends each line with the URL of each id on it, once, and leaves a linked id, "
              "a colour and a 6-digit number alone",
              ado_linked(f"#4511 OK parent -> #3247, #4511 again\nfill #333333 #9E9E9E #123456\n"
                         f"#1245 {u(1245)}", o, pj)
              == f"#4511 OK parent -> #3247, #4511 again  {u(4511)}  {u(3247)}\nfill #333333 #9E9E9E #123456\n"
                 f"#1245 {u(1245)}")
        check("ado_linked leaves text alone when org or project is unset",
              ado_linked("#4511 done", None, "P") == "#4511 done")
        check("ado_linked takes a link with no trailing slash, or a markdown link's, as linked",
              ado_linked(f"#4511 {u(4511)[:-1]}\n[#4511]({u(4511)[:-1]})", o, pj)
              == f"#4511 {u(4511)[:-1]}\n[#4511]({u(4511)[:-1]})")
        check("ado_url builds an item's link, and is None with org or project unset or a non-numeric id",
              ado_url(1245, "https://dev.azure.com/Org/", "My Project")
              == "https://dev.azure.com/Org/My%20Project/_workitems/edit/1245/"
              and ado_url(1245, None, "P") is None and ado_url("12x", "o", "p") is None)

        # The tools read it: run them as a separate process from inside the planted project.
        r = tool(root, deep, "import ado_rest, ado_write, ado\n"
                             "print(ado_rest.ORG, ado_rest.PROJECT, ado_write.ORG, ado_write.PROJECT, "
                             "ado.ORG_DEFAULT, ado.PROJ_DEFAULT)\n"
                             "print(bool(ado.TITLE_RE.match('T // Home - Hero // x')), "
                             "bool(ado.TITLE_RE.match('Other // Home - Hero // x')))")
        want = ("https://dev.azure.com/UserOrg Theirs https://dev.azure.com/UserOrg Theirs "
                "https://dev.azure.com/UserOrg Theirs\nTrue False")
        check("ado.py, ado_rest.py and ado_write.py take the org, project and title prefix from it",
              r.stdout.strip() == want, (r.stdout + r.stderr).strip()[-300:])
        if have_fc:
            r = tool(root, deep, "import figma_comments as fc\nprint(list(fc.KNOWN_FILES))")
            check("figma_comments.py takes the files from it", r.stdout.strip() == "['KEY1']",
                  (r.stdout + r.stderr).strip()[-300:])
        os.remove(os.path.join(home, FILE))  # the planted one: ~ is the real one again here
        r = tool(root, bare, "import ado_rest\nprint(ado_rest.ORG, ado_rest.PROJECT)")
        check("with no file they still import, with nothing set", r.returncode == 0 and r.stdout.strip()
              == "None None", (r.stdout + r.stderr).strip()[-300:])
        r = tool(root, bare, "import sys, ado_rest\nsys.argv = ['ado_rest.py', 'pull']\n"
                             "import kit_config\nsys.exit(kit_config.run(ado_rest.main))")
        check("a tool that needs ADO with nothing set exits 2 and says what to set, before any call",
              r.returncode == 2 and "not configured: ado.org" in r.stderr, f"exit {r.returncode}: "
              + r.stderr.strip()[-300:])
        r = tool(root, bare, "import ado\nprint(bool(ado.TITLE_RE.match('anything at all')))")
        check("with no title_prefix set, any title passes the convention", r.stdout.strip() == "True",
              (r.stdout + r.stderr).strip()[-300:])
        r = tool(root, bare, "import kit_config\nprint(kit_config.token('KC_SELFTEST_A', 'KC_SELFTEST_B'))",
                 {"KC_SELFTEST_B": "from-env"})
        check("token() reads the first variable that is set", r.stdout.strip() == "from-env",
              (r.stdout + r.stderr).strip()[-300:])
        plugin_checks(root)

    def plugin_checks(root):
        """A run started inside the plugin's own folder reads the project only when it is named."""
        global PLUGIN
        plug, pproj = os.path.join(root, "plugin"), os.path.join(root, "pproj")
        write(os.path.join(plug, ".claude-plugin", "plugin.json"), {"name": NAME})
        os.makedirs(os.path.join(plug, "tools"), exist_ok=True)
        write(os.path.join(pproj, FILE), {"ado": {"project": "Named"}})
        write(os.path.join(root, "copy", "tools", "x.py"), "")
        write(os.path.join(root, "other", ".claude-plugin", "plugin.json"), {"name": "another"})
        os.makedirs(os.path.join(root, "other", "tools"), exist_ok=True)
        check("the plugin's folder holds .claude-plugin/plugin.json named product-os; a copy of the "
              "tools, or another plugin, is not taken for it",
              _plugin_root(os.path.join(plug, "tools")) == plug
              and _plugin_root(os.path.join(root, "copy", "tools")) is None
              and _plugin_root(os.path.join(root, "other", "tools")) is None)
        saved = (PLUGIN, os.getcwd(), os.environ.pop("CLAUDE_PROJECT_DIR", None), os.environ.get("OLDPWD"),
                 {k: os.environ.get(k) for k in HOME_VARS})
        PLUGIN = plug
        try:
            # An empty home, so the person's own settings can't answer need() for the planted project.
            os.environ.update(home_env(os.path.join(root, "plugin-home")))
            os.makedirs(os.path.join(root, "plugin-home", ".claude"), exist_ok=True)
            os.chdir(os.path.join(plug, "tools"))
            os.environ["OLDPWD"] = pproj
            reset()
            try:
                project_dir()
                raised = ""
            except InPluginFolder as e:
                raised = str(e)
            c = load()
            try:
                need("ado", "project")
                needed = ""
            except NotConfigured as e:
                needed = str(e)
            check("started inside the plugin, nothing named: refused in one line naming the folder before "
                  "it; no project file read, and need() raises the same line",
                  raised.startswith("REFUSED:") and "\n" not in raised and pproj in raised
                  and c["project"] is None and c["refused"] == raised and needed == raised, raised or c)
            check("started inside the plugin, the project named with --project is read",
                  project_dir(pproj) == pproj and load(pproj)["project"] == os.path.join(pproj, FILE)
                  and get("ado", "project", start=pproj) == "Named")
            try:
                project_dir(plug)
                named = ""
            except InPluginFolder as e:
                named = str(e)
            check("--project naming the plugin's own folder is refused too, and the line names the "
                  "--project to use", named.startswith("REFUSED: --project ") and f"--project {pproj}." in named,
                  named)
            # Through the product-os command, macOS's /bin/sh has dropped OLDPWD.
            os.environ.pop("OLDPWD", None)
            reset()
            try:
                project_dir()
                blind = ""
            except InPluginFolder as e:
                blind = str(e)
            check("with no folder before it, the refusal says to run it where the session works, with no "
                  "cd, and not to read the project's file in its place",
                  "in the folder the session works in, with no cd first" in blind
                  and f"Don't read the project's {FILE} in its place" in blind and "\n" not in blind, blind)
            os.environ["OLDPWD"] = pproj
            example = os.path.join(plug, "examples", "proj")
            write(os.path.join(example, FILE), {"ado": {"project": "Example"}})
            os.chdir(os.path.join(example))
            os.makedirs("src", exist_ok=True)
            os.chdir("src")
            reset()
            check("a project inside the plugin, with its own .claude folder, is a project: named or run in",
                  project_dir(example) == example and get("ado", "project") == "Example")
            os.chdir(os.path.join(plug, "tools"))
            os.environ["CLAUDE_PROJECT_DIR"] = pproj
            reset()
            check("started inside the plugin, CLAUDE_PROJECT_DIR names the project",
                  project_dir() == pproj and get("ado", "project") == "Named")
            os.environ.pop("CLAUDE_PROJECT_DIR")
            os.chdir(pproj)
            reset()
            check("outside the plugin the working folder is the project, as before",
                  os.path.realpath(project_dir()) == os.path.realpath(pproj) and load()["refused"] is None
                  and get("ado", "project") == "Named")
        finally:
            PLUGIN = saved[0]
            os.chdir(saved[1])
            for k, v in (("CLAUDE_PROJECT_DIR", saved[2]), ("OLDPWD", saved[3]), *saved[4].items()):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            reset()

    with tempfile.TemporaryDirectory() as root:
        checks(root)
    ok_base = all(ok for _, ok in base)
    if not have_fc:
        print("  (figma_comments.py is not installed beside this file, so its check did not run)")
    print("mutations: each rule broken on purpose must fail a check above")
    for m in ("no_walk", "user_wins", "no_env", "no_withhold", "no_cmd_suffix",
              "no_plugin_guard", "no_repo_key", "no_dangling", "no_isolate"):
        MUT.clear()
        MUT.add(m)
        n = len(base)
        with tempfile.TemporaryDirectory() as root:
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                checks(root)
        caught = not all(ok for _, ok in base[n:])
        del base[n:]
        results.append(caught)
        print(f"  {'CAUGHT' if caught else 'MISSED'}  {m}")
    MUT.clear()
    reset()
    print(f"{sum(ok for _, ok in base)} of {len(base)} checks passed; {sum(results)} of {len(results)} "
          "mutations caught")
    return 0 if ok_base and all(results) else 1


if __name__ == "__main__":
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print(__doc__)
        sys.exit(0)
    args, start = sys.argv[1:], None
    if "--project" in args and args.index("--project") + 1 < len(args):
        i = args.index("--project")
        start = args[i + 1]
        del args[i:i + 2]
    if args[:1] == ["accept"]:
        sys.exit(accept(args[1:], start))
    sys.exit(selftest() if args[:1] == ["--selftest"] else show(start))
