"""Run the unit tests in parallel, and print the first failures as GitHub Actions error
annotations, so the reason shows on the run page and through the public checks API without
opening the job log.

    python .github/run_tests.py [-j N] [--no-cache] [--record] [name ...]

It finds the tests the way `python -m unittest discover -s tests` does and runs them in N worker
processes, one per CPU up to 8 by default; -j 1 runs them in this process. A name keeps the tests whose
id contains it. A class's tests run in batches of a few at a time, and its setUpClass, such as
the gate tests' one browser, runs once for each batch. tests/durations.json, which --record
rewrites, gives each test's time; batches are sized from it, and the longest start first.

Locally, a test that passed is skipped while nothing it depends on has changed, and is reported
as "ok (cached)". What a test depends on is recorded while its module's tests run: every file in
the repository they read, listed or checked was there, the size and time of anything else they
read outside the temp folder and the standard library, the Python version, the platform, the
installed packages, the environment variables ENV_KEYS names and this file. A file that changes
while its tests run counts as changed. A new environment variable a test reads goes in ENV_KEYS.
Not seen: whether a path outside the repository is there, when nothing reads it; a repository
file's time or mode, and its size when nothing reads it; a new module that shadows an import,
earlier on sys.path; a function's docstring read without the function running; and what
Playwright's driver and its browser read themselves. With PLAYWRIGHT_NODEJS_PATH set, the driver
counts as any other program.
From Python 3.12, a Python file they imported counts by its outline, the file without its
function bodies, and by each function that ran, so an edit to a function none of them ran, or
to a comment, runs nothing again. Browser tests count each file on their stack whole, since
Playwright reads its source. A test that starts a program, other than Playwright's own
driver, is never skipped, since what that program reads can't be seen. The record is
.cache/test-results.json. --no-cache runs every test, and so does CI, where CI is set.
"""
import argparse
import ast
import concurrent.futures
import faulthandler
import hashlib
import importlib
import importlib.util
import json
import linecache
import multiprocessing
import os
import pathlib
import platform
import re
import secrets
import sys
import tempfile
import threading
import time
import types
import unittest

SELF = os.path.realpath(__file__)
ROOT = os.path.dirname(os.path.dirname(SELF))
CACHE = os.path.join(ROOT, ".cache", "test-results.json")
DURATIONS = os.path.join(ROOT, "tests", "durations.json")
MAX_NOTES = 10  # GitHub keeps 10 error annotations per step
UNKNOWN = 0.05  # seconds, for a test durations.json doesn't list
# More workers than this made the suite no faster on an 18-core Mac. Starting programs and
# running Chromium were the limits, and a browser test timed out once at 18.
MAX_JOBS = 8
HANG_S = 600  # a test still running after this prints its stack
# A file's time comes from a coarser clock than time.time_ns(): a few ms on Linux, about 16 on
# Windows. An edit this close before a batch starts still counts as made during it.
CLOCK_NS = 20_000_000
# The environment variables the tests and the code they run read, by name or by prefix. OLDPWD
# is left out, since every cd changes it: the tests that read it set it themselves.
ENV_KEYS = ("PATH", "PATHEXT", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP", "REQUIRE_SHELLS",
            "ANTHROPIC_IDENTITY_TOKEN_FILE", "CLAUDE_PROJECT_DIR", "CLAUDE_CONFIG_DIR", "CLAUDE_PLUGIN_",
            "CLAUDE_CODE_GIT_BASH_PATH", "CLAUDE_CODE_FEDERATION", "PRODUCT_OS_")
CHANGED = "changed while its tests ran"  # a value no later check returns


def escape(text, prop=False):
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if prop else text


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def module_of(test_id):
    return test_id.split(".", 1)[0]


# What a worker records while a batch runs: the paths read or listed, each program started, as
# True when it is Playwright's driver, and from Python 3.12 each function that ran.
STATE = {"ready": False, "reads": None, "spawns": [], "driver": None, "ran": None, "since": None}
MONITOR = getattr(sys, "monitoring", None)
TOOL = 3  # a sys.monitoring tool id Python leaves free
SPAWNS = ("subprocess.Popen", "os.posix_spawn", "os.spawn", "os.system", "os.exec", "os.startfile", "os.fork",
          "os.forkpty", "_posixsubprocess.fork_exec", "_winapi.CreateProcess")


def audit(event, args):
    reads = STATE["reads"]
    if reads is None:
        return
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        if not isinstance(path, str):
            return
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            return
        if mode is None and isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR):
            return
        try:
            importing = sys._getframe(1).f_code.co_filename.startswith("<frozen importlib")
        except ValueError:
            importing = False
        reads.add(("code" if importing and MONITOR else "file", os.path.abspath(path)))
    elif event in ("os.listdir", "os.scandir"):
        try:  # the import system lists sys.path folders; a new file there changes no import already made
            if sys._getframe(1).f_code.co_filename.startswith("<frozen importlib"):
                return
        except ValueError:
            pass
        path = args[0] if args else "."
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        if isinstance(path, str) or path is None:
            reads.add(("dir", os.path.abspath(path or ".")))
    elif event in SPAWNS:
        try:
            STATE["spawns"].append(is_driver(event, args, STATE["driver"]))
        except Exception:  # can't tell: count it as a program, so its test always runs
            STATE["spawns"].append(False)


def program_of(event, args):
    """The program a start's audit event runs, or None when it can't be told, as for a shell
    command, os.system or a fork. Its other arguments, folder and environment don't count."""
    def first(text):
        found = re.match(r'\s*(?:"([^"]*)"|(\S+))', os.fsdecode(text))
        return found and (found.group(1) or found.group(2))

    if event == "subprocess.Popen":  # (executable, args, cwd, env)
        executable, argv = args[0], args[1]
        if executable is not None:
            return os.fsdecode(executable)
        if isinstance(argv, (list, tuple)):
            return os.fsdecode(argv[0]) if argv else None
        return first(argv) if isinstance(argv, (str, bytes)) else os.fsdecode(argv)
    if event in ("os.posix_spawn", "os.exec"):  # (path, argv, env)
        return os.fsdecode(args[0])
    if event == "os.spawn":  # (mode, path, args, env)
        return os.fsdecode(args[1])
    if event == "_winapi.CreateProcess":  # (application name, command line, current folder)
        return os.fsdecode(args[0]) if args[0] else first(args[1]) if args[1] else None
    if event == "_posixsubprocess.fork_exec":  # (executables, args, env), from Python 3.14
        executables = args[0] or ()
        # Several are a PATH search, and so is one from a one-folder PATH; the subprocess.Popen
        # event for the same start names the bare program, which doesn't count.
        return os.fsdecode(executables[0]) if len(executables) == 1 else None
    return None


def is_driver(event, args, driver):
    """Whether a program start runs Playwright's driver: the program it runs has an absolute path
    in the driver's folder."""
    program = program_of(event, args) if driver else None
    return bool(program) and os.path.isabs(program) and os.path.normpath(program).startswith(driver)


def watch_parent():
    """End this worker when the runner that started it is gone, so a killed run leaves no
    workers or browsers behind. A worker waiting for work never notices on its own."""
    def watch():
        multiprocessing.parent_process().join()
        os._exit(1)
    threading.Thread(target=watch, daemon=True).start()


def noting(real):
    """os.stat or os.lstat, also noting a path in the repository it's asked about, so a test
    that only checks whether a file is there depends on it."""
    def call(path, *args, **kwargs):
        reads = STATE["reads"]
        if reads is not None and isinstance(path, (str, bytes, os.PathLike)):
            try:
                where = os.path.abspath(os.fsdecode(path))
            except (TypeError, ValueError):
                where = ""
            if inside(where):
                reads.add(("exists", where))
        return real(path, *args, **kwargs)
    return call


def setup_worker():
    if STATE["ready"]:
        return
    STATE["ready"] = True
    spec = importlib.util.find_spec("playwright")
    if spec and spec.origin:
        STATE["driver"] = os.path.join(os.path.dirname(spec.origin), "driver") + os.sep
    sys.addaudithook(audit)
    # No audit event says a path was checked. os.path and pathlib call os.stat, except where
    # they are built in: os.path on Windows from Python 3.12, and pathlib before 3.11.
    for name in ("stat", "lstat"):
        real, wrapped = getattr(os, name), noting(getattr(os, name))
        for group in (os.supports_dir_fd, os.supports_fd, os.supports_follow_symlinks, os.supports_effective_ids):
            if real in group:
                group.add(wrapped)  # shutil asks these sets about os.stat by identity
        setattr(os, name, wrapped)
    for name in ("exists", "lexists", "isfile", "isdir", "islink"):
        if not isinstance(getattr(os.path, name, None), types.FunctionType):
            setattr(os.path, name, noting(getattr(os.path, name)))
    accessor = getattr(pathlib, "_NormalAccessor", None)
    if accessor is not None:
        accessor.stat, accessor.lstat = staticmethod(os.stat), staticmethod(os.lstat)
    if MONITOR:
        MONITOR.use_tool_id(TOOL, "run_tests")
        MONITOR.register_callback(TOOL, MONITOR.events.PY_START, started)
        MONITOR.set_events(TOOL, MONITOR.events.PY_START)


def started(code, offset):
    """Note the function, once a batch: DISABLE stops the calls until the next batch."""
    ran = STATE["ran"]
    if ran is not None:
        ran.add((code.co_filename, code.co_qualname))
    return MONITOR.DISABLE


def purge():
    """Forget the repository's modules, so a batch imports them afresh and its reads show what
    its module depends on."""
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None)
        if name not in ("__main__", "__mp_main__") and where and inside(os.path.realpath(where)):
            del sys.modules[name]
    importlib.invalidate_caches()


def inside(path):
    """Whether a path is the project's own: in the repository, and not in a virtualenv kept there."""
    return (path == ROOT or path.startswith(ROOT + os.sep)) and not path.startswith(PYTHON_HOMES)


PYTHON_HOMES = tuple({os.path.realpath(p) + os.sep for p in (sys.prefix, sys.exec_prefix, sys.base_prefix)})


UNLISTED = {".cache", ".git", "__pycache__", ".DS_Store"}  # names a folder's listing leaves out
SKIPPED_ROOTS = tuple(os.path.realpath(p) + os.sep for p in
                      {tempfile.gettempdir(), "/tmp", "/private/tmp", "/private/var/folders", "/dev", "/proc",
                       sys.base_prefix})


def stamp(kind, path, memo=None):
    """(key, value) recording one input, or None for one that isn't recorded: a file in the
    repository by its content, a folder there by its names, a file elsewhere by size and time."""
    path = source_of(path) or path
    real = os.path.realpath(path)
    if real == SELF:  # Playwright reads the source of each file on the stack; this one is in the stamp
        return None
    if inside(real):
        path = real
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rel.split("/")[0] in (".git", ".cache"):
            return None
        key = f"{kind}:{rel}"
        if memo is not None and key in memo:
            return key, memo[key]
        try:
            info = os.stat(path)
        except OSError:
            info = None
        try:
            since = STATE["since"]
            if info is None:
                value = "missing"
            elif since and info.st_mtime_ns >= since:
                value = CHANGED
            elif kind == "exists":  # that it's there and what it is: Path(__file__).resolve() checks every file
                value = "folder" if os.path.isdir(path) else "file"
            elif kind == "dir":
                if not os.path.isdir(path):
                    value = "not a folder"
                else:
                    names = sorted(n for n in os.listdir(path) if n not in UNLISTED)
                    value = digest("\n".join(names))
            elif os.path.isfile(path):
                with open(path, "rb") as handle:
                    value = hashlib.sha256(handle.read()).hexdigest()[:20]
            else:
                value = "not a file"
        except OSError as err:
            value = f"unreadable {err.errno}"
        if memo is not None:
            memo[key] = value
        return key, value
    if kind != "file" or real.startswith(SKIPPED_ROOTS) or os.path.isdir(real):
        return None
    try:
        info = os.stat(real)
    except OSError:
        return f"ext:{real}", "missing"
    if STATE["since"] and info.st_mtime_ns >= STATE["since"]:
        return f"ext:{real}", CHANGED
    return f"ext:{real}", f"{info.st_size}:{info.st_mtime_ns}"


OUTLINES = {}  # path: (size and time, its outline)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def outline(path):
    """(a hash of the Python file with every function body left out, {qualified name: a hash of
    that function}), or None when it doesn't parse. Comments, blank lines and line numbers are
    part of neither, so moving or reformatting code changes nothing."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    seen = OUTLINES.get(path)
    if seen and seen[0] == (info.st_size, info.st_mtime_ns):
        return seen[1]
    try:
        with open(path, "rb") as handle:
            tree = ast.parse(handle.read())
    except (OSError, SyntaxError, ValueError):
        found = None
    else:
        defs, classes = {}, set()

        def visit(node, prefix):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = prefix + child.name  # two defs of one name share a hash
                    defs[name] = digest(defs.get(name, "") + ast.dump(child))
                    child.body = [ast.Pass()]
                elif isinstance(child, ast.ClassDef):
                    classes.add(prefix + child.name)
                    visit(child, prefix + child.name + ".")
                else:
                    visit(child, prefix)

        visit(tree, "")
        found = (digest(ast.dump(tree)), defs, classes)
    OUTLINES[path] = ((info.st_size, info.st_mtime_ns), found)
    return found


def code_stamps(path, ran):
    """What a batch that imported this Python file in the repository depends on in it: its
    outline, and each of its functions that ran. A function that ran inside another stands for
    the outer one. Code that can't be placed holds the whole file."""
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    try:
        if STATE["since"] and os.stat(path).st_mtime_ns >= STATE["since"]:
            return [(f"file:{rel}", CHANGED)]
    except OSError:
        pass
    found = outline(path)
    if found is None:
        return [stamp("file", path)]
    whole, defs, classes = found
    pairs = [(f"outline:{rel}", whole)]
    for name in sorted(ran):
        outer = name.split(".<locals>.")[0]
        if outer in defs:
            pairs.append((f"def:{rel}:{outer}", defs[outer]))
        elif not (outer == "<module>" or outer in classes or outer.rsplit(".", 1)[-1].startswith("<")):
            return [stamp("file", path)]
    return pairs


def source_of(path):
    """The source file behind a cached .pyc, in __pycache__ or under sys.pycache_prefix, or the
    path itself; None for a .pyc with no source."""
    if not path.endswith(".pyc"):
        return path
    try:
        return importlib.util.source_from_cache(path)
    except ValueError:
        return None if "__pycache__" in path.split(os.sep) else path


def recheck(key, memo):
    kind, _, where = key.partition(":")
    if kind in ("outline", "def"):
        rel, _, name = where.rpartition(":") if kind == "def" else (where, "", "")
        found = outline(os.path.join(ROOT, *rel.split("/")))
        if found is None:
            return "gone"
        return found[0] if kind == "outline" else found[1].get(name, "missing")
    if kind == "ext":
        found = stamp("file", where)
        return found[1] if found else "gone"
    found = stamp(kind, os.path.join(ROOT, *where.split("/")), memo)
    return found[1] if found else "gone"


class Collect(unittest.TestResult):
    """One row per test: its id, status, seconds, error texts, and whether it started a program
    other than Playwright's driver. Each test's output is held back, as unittest's -b does."""

    def __init__(self):
        super().__init__()
        self.buffer = True
        self.rows, self.row, self.mark, self.inside_spawns = [], None, 0, 0

    def startTest(self, test):
        faulthandler.dump_traceback_later(HANG_S)  # a test that hangs shows where, in the log
        super().startTest(test)
        self.row = {"id": test.id(), "name": str(test), "status": "ok", "errors": [], "spawned": False}
        self.started, self.mark = time.perf_counter(), len(STATE["spawns"])

    def stopTest(self, test):
        faulthandler.cancel_dump_traceback_later()
        self._mirrorOutput = False  # its output is printed with the failure, once
        super().stopTest(test)
        if self.row is None:
            return
        mine = STATE["spawns"][self.mark:]
        self.row["spawned"] = not all(mine)
        self.inside_spawns += sum(not d for d in mine)
        self.row["seconds"] = round(time.perf_counter() - self.started, 3)
        self.rows.append(self.row)
        self.row = None

    def note(self, test, kind, err=None, text=None):
        """Record a failure: the traceback with the test's output, to print, and without it, for
        the annotation, so output can't push the reason out of its last lines."""
        if text is None:
            text = self._exc_info_to_string(err, test)
            buffered, self.buffer = self.buffer, False
            try:
                trace = self._exc_info_to_string(err, test)
            finally:
                self.buffer = buffered
        else:
            trace = text
        entry = [kind, str(test), text, trace]
        if self.row is not None and (test.id() == self.row["id"] or str(test).startswith(self.row["name"])):
            if self.row["status"] in ("ok", "skip"):
                self.row["status"] = kind
            self.row["errors"].append(entry)
        else:  # a setUpClass or tearDownClass error, outside any test
            self.rows.append({"id": test.id(), "name": str(test), "status": kind, "errors": [entry],
                              "spawned": True, "seconds": 0, "outside": True})

    def _restoreStdout(self):
        if self.row is None and self.buffer:  # a class or module setup: show what it printed
            self._mirrorOutput = True
        super()._restoreStdout()

    def addError(self, test, err):
        super().addError(test, err)
        self.note(test, "error", err)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.note(test, "fail", err)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.note(subtest, "fail" if issubclass(err[0], test.failureException) else "error", err)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if self.row is not None:
            self.row["skips"] = self.row.get("skips", 0) + 1  # unittest counts each one
            if self.row["status"] == "ok":  # a subtest that failed before keeps the failure
                self.row["status"], self.row["reason"] = "skip", reason
        else:  # setUpClass skipped the whole class
            self.rows.append({"id": test.id(), "name": str(test), "status": "skip", "reason": reason, "errors": [],
                              "spawned": True, "seconds": 0, "outside": True, "skips": 1})

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.row["status"] = "expected failure"

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.note(test, "unexpected success", text="the test is marked as an expected failure but passed\n")


def run_batch(ids, cache):
    """Run these tests, all from one class, in this process. With cache, also record what they
    read. (rows, inputs, whether the class's setup started a program)."""
    if cache:
        setup_worker()
    cwd, env = os.getcwd(), dict(os.environ)
    reads = set()
    if cache:
        purge()
        linecache.clearcache()  # so source read for a stack is read, and seen, in every batch
        if MONITOR:
            STATE["ran"] = set()
            MONITOR.restart_events()
        STATE["since"] = time.time_ns() - CLOCK_NS
    STATE["reads"], STATE["spawns"] = (reads if cache else None), []
    result = Collect()
    try:
        unittest.defaultTestLoader.loadTestsFromNames(ids).run(result)
    finally:
        STATE["reads"] = None
        ran, STATE["ran"] = STATE["ran"] or set(), None
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(env)
    module = sys.modules.get(module_of(ids[0]))
    if cache and getattr(module, "__file__", None):
        reads.add(("code" if MONITOR else "file", os.path.abspath(module.__file__)))
    ran_in, real_of = {}, {}
    for filename, name in ran:
        if not filename.startswith("<"):
            if filename not in real_of:
                real_of[filename] = os.path.realpath(filename)
            ran_in.setdefault(real_of[filename], set()).add(name)
    inputs, memo = {}, {}
    for kind, path in sorted(reads):
        if kind == "code":
            source = source_of(path)
            real = source and os.path.realpath(source)
            if not real:
                continue
            if inside(real) and real != SELF and real.endswith(".py"):
                pairs = code_stamps(real, ran_in.get(real, ()))
            else:
                pairs = [stamp("file", real, memo)]
        else:
            pairs = [stamp(kind, path, memo)]
        for found in pairs:
            if found:
                inputs[found[0]] = found[1]
    STATE["since"] = None
    setup_spawned = sum(not d for d in STATE["spawns"]) > result.inside_spawns
    return result.rows, inputs, setup_spawned


def batches(tests, durations, jobs):
    """Each class's tests in runs of about a quarter of one worker's share of the work, so the
    last runs to finish are short, longest first. A test longer than that runs alone."""
    weight = {t: float(durations.get(t, UNKNOWN)) for t in tests}
    share = sum(weight.values()) / max(jobs * 4, 1)
    classes = {}
    for t in tests:
        classes.setdefault(t.rsplit(".", 1)[0], []).append(t)
    out = []
    for ids in classes.values():
        run, total = [], 0.0
        for t in ids:
            if run and total + weight[t] > share:
                out.append((total, run))
                run, total = [], 0.0
            run.append(t)
            total += weight[t]
        out.append((total, run))
    return [ids for _, ids in sorted(out, key=lambda pair: -pair[0])]


def environment_stamp():
    digest = hashlib.sha256()
    with open(SELF, "rb") as handle:
        digest.update(handle.read())
    digest.update(f"{sys.version}|{platform.platform()}|{sys.executable}".encode())
    for key in sorted(os.environ):
        if key.startswith(ENV_KEYS):
            digest.update(f"|{key}={os.environ[key]}".encode())
    try:  # a package imported before a batch starts isn't read again, so its version stands in
        from importlib import metadata
        packages = sorted(f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions())
    except Exception:
        packages = []
    digest.update("|".join(packages).encode())
    return digest.hexdigest()


def load_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".", suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(data, out, indent=1, sort_keys=True)
        out.write("\n")
    os.replace(temp, path)


def fresh_modules(record, modules):
    """The modules whose recorded inputs all still read the same."""
    memo, fresh = {}, set()
    for name in modules:
        inputs = (record.get("modules") or {}).get(name)
        if isinstance(inputs, dict) and inputs and all(recheck(k, memo) == v for k, v in inputs.items()):
            fresh.add(name)
    return fresh


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-j", "--jobs", type=int, default=min(os.cpu_count() or 1, MAX_JOBS))
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--record", action="store_true", help="rewrite tests/durations.json")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    sys.path[0] = ROOT  # as `python -m unittest` has it: the repo root, not .github/
    started = time.perf_counter()
    found = list(flatten(unittest.defaultTestLoader.discover("tests")))
    broken = [t for t in found if type(t).__module__ == "unittest.loader"]  # a module that didn't import
    tests = [t.id() for t in found if t not in broken]
    importable = {module_of(t) for t in tests}
    if args.names:
        tests = [t for t in tests if any(name in t for name in args.names)]
        # A module that didn't import stands for its tests, which may hold any name: it's left out
        # only when every name is inside another module, one that did import, such as
        # test_many.ManyTest. A bare name, even a module's, may match a test of any module. With no
        # test left, every one is kept, to say why.
        def asked(module):
            return any(name in module or name.startswith(module + ".")
                       or not any(name.startswith(other + ".") for other in importable) for name in args.names)
        broken = [t for t in broken if asked(t._testMethodName)] if tests else broken
    if not tests and not broken:
        print("NO TESTS RAN")
        return 5  # as unittest exits
    cache = not args.no_cache and not os.environ.get("CI")
    env = environment_stamp()
    record = load_json(CACHE) if cache else {}
    if record.get("stamp") != env:
        record = {}
    fresh = fresh_modules(record, {module_of(t) for t in tests}) if cache else set()
    passed_before = set(record.get("passed") or [])
    cached = sorted(t for t in tests if t in passed_before and module_of(t) in fresh)
    skipped = set(cached)
    to_run = [t for t in tests if t not in skipped]
    for t in cached:
        print(f"{t} ... ok (cached)", flush=True)

    rows, inputs, setup_spawned, notes, outside = [], {}, set(), [0], set()

    def take(batch_rows, batch_inputs, spawned_in_setup, ids):
        mine = inputs.setdefault(module_of(ids[0]), {})
        for key, value in batch_inputs.items():  # two batches that saw a file differently: it changed
            mine[key] = value if mine.get(key, value) == value else CHANGED
        if spawned_in_setup or any(row.get("outside") and row["status"] in ("fail", "error") for row in batch_rows):
            setup_spawned.update(ids)  # a setup or teardown that started a program or failed: run them again
        for row in batch_rows:
            if row.get("outside"):  # a class's setup runs in each of its batches: count it once
                if (row["status"], row["name"]) in outside:
                    continue
                outside.add((row["status"], row["name"]))
            rows.append(row)
            shown = {"ok": "ok", "skip": f"skipped {row.get('reason', '')!r}", "fail": "FAIL", "error": "ERROR",
                     "expected failure": "expected failure", "unexpected success": "unexpected success"}
            took = f" ({row['seconds']:.1f}s)" if row.get("seconds", 0) >= 1 else ""
            print(f"{row['name']} ... {shown.get(row['status'], row['status'])}{took}", flush=True)
            for kind, what, _, trace in row["errors"]:
                if notes[0] < MAX_NOTES:
                    notes[0] += 1
                    body = "\n".join(trace.rstrip().splitlines()[-15:])
                    print("::error title=%s::%s" % (escape("%s %s" % (kind.upper(), what), prop=True), escape(body)),
                          flush=True)

    work = batches(to_run, load_json(DURATIONS), args.jobs)
    if args.jobs <= 1 or len(work) <= 1:
        for ids in work:
            take(*run_batch(ids, cache), ids)
    else:
        context = multiprocessing.get_context("spawn")
        pool = concurrent.futures.ProcessPoolExecutor(max_workers=min(args.jobs, len(work)), mp_context=context,
                                                      initializer=watch_parent)
        try:
            futures = {pool.submit(run_batch, ids, cache): ids for ids in work}
            for future in concurrent.futures.as_completed(futures):
                take(*future.result(), futures[future])
        except BaseException:  # Ctrl-C, or the runner's own error: stop the workers, not just the queue
            for process in list((getattr(pool, "_processes", None) or {}).values()):
                process.terminate()
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown()
    for test in broken:  # its import error, run here
        result = Collect()
        test.run(result)
        take(result.rows, {}, False, ["unittest"])

    failed = [row for row in rows if row["status"] in ("fail", "error", "unexpected success")]
    # On GitHub, a line of a test's output that starts with "::" would be read as a command, such
    # as a stray annotation; between these two lines it's printed as it is.
    fence = secrets.token_hex(8) if failed and os.environ.get("GITHUB_ACTIONS") else ""
    if fence:
        print(f"::stop-commands::{fence}")
    for row in failed:
        for kind, what, text, _ in row["errors"]:
            print("=" * 70)
            print(f"{kind.upper()}: {what}")
            print("-" * 70)
            print(text.rstrip())
    if fence:
        print(f"::{fence}::")
    elapsed = time.perf_counter() - started
    print("-" * 70)
    print(f"Ran {sum(not row.get('outside') for row in rows)} tests in {elapsed:.3f}s" +
          (f"; {len(cached)} more passed before and were skipped, since nothing they read has changed"
           if cached else ""))
    counts = []  # as unittest counts them: each failed subtest, each skipped test
    for status, word in (("fail", "failures"), ("error", "errors"), ("skip", "skipped"),
                         ("expected failure", "expected failures"), ("unexpected success", "unexpected successes")):
        if status in ("fail", "error", "unexpected success"):
            n = sum(entry[0] == status for row in rows for entry in row["errors"])
        elif status == "skip":
            n = sum(row.get("skips", 0) for row in rows)
        else:
            n = sum(row["status"] == status for row in rows)
        if n:
            counts.append(f"{word}={n}")
    print(("FAILED" if failed else "OK") + (f" ({', '.join(counts)})" if counts else ""))

    if cache:
        save(record, env, fresh, tests, to_run, rows, inputs, setup_spawned)
    if args.record:
        durations = load_json(DURATIONS)
        durations.update({row["id"]: round(row["seconds"], 1) for row in rows
                          if not row.get("outside") and row["id"] in tests})
        write_json(DURATIONS, {k: durations[k] for k in sorted(durations)})
    return 1 if failed else 0


def save(record, env, fresh, tests, to_run, rows, inputs, setup_spawned):
    """Keep each module's inputs and the tests that passed without starting a program. A module
    whose inputs changed keeps only what ran this time."""
    old_modules = record.get("modules") or {}
    old_passed = set(record.get("passed") or [])
    modules, passed = {}, set()
    to_run = set(to_run)
    ran = {module_of(t) for t in to_run}
    memo = {}
    for name in set(old_modules) | ran:
        old = old_modules.get(name, {})
        if name in fresh and all(recheck(k, memo) == v for k, v in old.items()):
            # Unchanged from the start of the run to its end, so the tests skipped still stand.
            modules[name] = {**old, **inputs.get(name, {})}
            passed |= {t for t in old_passed if module_of(t) == name}
        elif name in ran or name in fresh:
            modules[name] = inputs.get(name, {})
        elif name not in {module_of(t) for t in tests}:
            modules[name] = old_modules[name]  # not asked for this time
            passed |= {t for t in old_passed if module_of(t) == name}
    for row in rows:
        passed.discard(row["id"])
        if row["status"] == "ok" and not row["spawned"] and row["id"] not in setup_spawned and row["id"] in to_run:
            passed.add(row["id"])
    passed = {t for t in passed if module_of(t) in modules}
    write_json(CACHE, {"stamp": env, "modules": modules, "passed": sorted(passed)})


if __name__ == "__main__":
    sys.exit(main())
