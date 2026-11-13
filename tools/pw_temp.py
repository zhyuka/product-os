#!/usr/bin/env python3
"""pw_temp.py - every browser run gets a temp folder of its own, and a killed run's folder is reaped.

WHY THIS EXISTS
  A bare `chromium.launch()` makes its profile (playwright_chromiumdev_profile-*) and an artifacts
  folder (playwright-artifacts-*) in the shared temp dir, and the browser writes its own temp files
  (com.google.chrome.for.testing.*, com.microsoft.edgemac.*, scoped_dir*) there too. A clean close
  deletes them. A run killed by a timeout never gets to, and nothing names the run that made them,
  so nothing can tell an orphan from a live run's folder. Tools that are often killed by timeouts
  leave hundreds of these behind.

  Playwright's driver takes its temp dir from its own environment, once, when it spawns, and the
  browser inherits that environment unless the caller passes `env=`. So `sync_playwright` here sets
  TMPDIR (TEMP and TMP on Windows, and MAC_CHROMIUM_TMPDIR, which Chromium on macOS reads first) to a
  folder named for this process, only while the driver spawns, and deletes the folder when the run
  ends.

  A killed run's folder stays, but its name carries the pid, so `reap` deletes it at the next launch
  once that process is gone. Another tool that names its own browser folders <prefix><pid>-<random>
  can add its prefix to PREFIXES and reap through here too.

  Every pw.chromium.launch and launch_persistent_context through here also starts the browser with
  RenderDocument off, so a page closed mid-navigation does not hang the tool (OFF_FEATURES says why).

USAGE
  from pw_temp import sync_playwright      # in place of playwright.sync_api's; same use
  python tools/pw_temp.py reap [--dry]     # delete the folders of killed runs now
  python tools/pw_temp.py --selftest

  Python's tempfile keeps the real temp dir: it is read before the environment changes, and the
  environment is put back as soon as the driver is up. Another thread that starts a process in
  that moment inherits the folder.

EXIT
  0 done, 1 a selftest case failed, 2 no command given.
"""
import functools, glob, os, re, shutil, subprocess, sys, tempfile, threading, time

# Every Chromium launch through here turns RenderDocument off. With it on, pg.close() on a page whose
# navigation is committing never returns, so a tool that closes a page after a timed-out load that
# landed late hangs there. A planted late document (late_close below) hung every close under
# Playwright's own flags and none with RenderDocument off. microsoft/playwright#42068, open;
# late_close's calibration says when the browser no longer hangs, and then this can go.
# Chromium reads only the last --disable-features, and Playwright puts its own before the caller's
# args, so the one switch here starts with Playwright's list, read from the installed driver. A bare
# --disable-features=RenderDocument turns Playwright's disabled features (HTTPS upgrades among them)
# back on. A caller's --enable-features would replace Playwright's the same way; no tool here passes one.
OFF_FEATURES = ("RenderDocument",)
PREFIX = "pw-run-"   # pw-run-<pid>-<random>; the random part stops `pkill -f pw-run-123` matching pw-run-1234
# Every folder named <prefix><pid>-: this module's, plus any other tool's that names its browser
# folders the same way (add its prefix here).
PREFIXES = (PREFIX, "edge-run-", "gpushot-")
MIN_AGE = 1800   # a second guard for a live run
# Names Playwright and Chrome for Testing give their temp items, with no pid in them. Only `reap`
# with legacy_age touches these, after checking that no running process names the folder.
LEGACY = ("playwright_chromiumdev_profile-", "playwright-artifacts-", "com.google.chrome.for.testing.")
ENV_KEYS = ("TMPDIR", "TEMP", "TMP", "MAC_CHROMIUM_TMPDIR")
_WIN = os.name == "nt"
_env_lock = threading.Lock()


def _alive(pid):
    if _WIN:
        return alive_on_windows(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True   # alive under another user


STILL_ACTIVE, ACCESS_DENIED, QUERY_LIMITED_INFORMATION = 259, 5, 0x1000


def alive_on_windows(pid, kernel32=None, last_error=None):
    """Whether pid runs, on Windows: OpenProcess, then GetExitCodeProcess. os.kill(pid, 0) is no test
    there: signal 0 is CTRL_C_EVENT, which Python hands to GenerateConsoleCtrlEvent, and Microsoft
    documents that call as succeeding for a nonzero group id with nobody receiving the signal, so a
    gone pid would read alive. Access denied means it runs under another user. signed_in_browser and
    upkeep ask this too. kernel32 and last_error stand in for the real ones in the selftest; not yet
    measured on Windows."""
    import ctypes
    if not isinstance(pid, int) or pid <= 0:
        return False
    if kernel32 is None:
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        last_error = ctypes.get_last_error
    handle = kernel32.OpenProcess(QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return last_error() == ACCESS_DENIED
    try:
        code = ctypes.c_ulong(0)
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.pointer(code))) and code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _running_args():
    """Every running process's command line, joined, or None when ps could not run."""
    try:
        return subprocess.run(["ps", "-axww", "-o", "args="], capture_output=True, text=True,
                              timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def kill_pattern(path):
    """The pkill -f pattern for the processes that name this folder: its name as a whole path component.
    A bare name is a substring match: playwright_chromiumdev_profile-f would also match a live browser
    on .../playwright_chromiumdev_profile-fAb123/ (the selftest plants that decoy)."""
    name = "".join("\\" + c if c in ".[]()*+?{}|^$\\" else c for c in os.path.basename(path))
    return "/" + name + "(/|[[:space:]]|$)"


def remove(path):
    # A browser that outlived its killed run still holds the folder: stop it first. The folder is in that
    # browser's --user-data-dir, so pkill -f finds the re-parented renderer as well.
    if not _WIN:
        try:
            subprocess.run(["pkill", "-9", "-f", kill_pattern(path)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
        except (OSError, subprocess.SubprocessError):
            pass
    for _ in range(12):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass
        if not os.path.lexists(path):
            return True
        time.sleep(0.5)
    return False


def reap(root=None, dry=False, now=None, alive=_alive, legacy_age=None, args=None):
    """Delete the folders of runs that are gone; return their paths (with dry, delete nothing).

    A folder named <prefix><pid>- goes once that pid is gone and the folder is MIN_AGE old. With
    legacy_age (seconds), a LEGACY item that old also goes, unless a running process's command line
    names it; args stands in for ps in the selftest. On Windows the pid comes from alive_on_windows,
    and legacy items stay, since there is no ps to say what runs (not yet measured there)."""
    if _WIN and args is None:
        legacy_age = None
    root = root or tempfile.gettempdir()
    now = time.time() if now is None else now
    gone = []
    try:
        names = os.listdir(root)
    except OSError:
        return gone
    if legacy_age is not None and args is None and any(n.startswith(LEGACY) for n in names):
        args = _running_args()
        if args is None:
            legacy_age = None   # cannot see what is running, so leave the pid-less items alone
    for name in sorted(names):
        path = os.path.join(root, name)
        try:
            age = now - os.lstat(path).st_mtime
        except OSError:
            continue   # it went meanwhile
        prefix = next((p for p in PREFIXES if name.startswith(p)), None)
        if prefix:
            m = re.match(r"(\d+)-", name[len(prefix):])
            if not m or not os.path.isdir(path) or age < MIN_AGE or alive(int(m.group(1))):
                continue
        elif legacy_age is not None and name.startswith(LEGACY):
            if age < legacy_age or name in args:
                continue
        else:
            continue
        if dry or remove(path):
            gone.append(path)
    return gone


_PW_OFF = []


def playwright_disabled():
    """The features the installed Playwright disables at every Chromium launch (chromiumSwitches in its
    driver), read once per process. Raises when the list is not there or holds anything but names, so
    an upgrade that moves it stops every launch instead of turning those features back on."""
    if not _PW_OFF:
        import playwright
        lib = os.path.join(os.path.dirname(playwright.__file__), "driver", "package", "lib")
        for f in sorted(glob.glob(os.path.join(lib, "**", "*.js"), recursive=True)):
            with open(f, encoding="utf-8", errors="replace") as fh:
                names = _disabled_in(fh.read(), f)
            if names:
                _PW_OFF.extend(names)
                break
        else:
            raise RuntimeError(f"pw_temp: no disabledFeatures list under {lib}; Playwright's own "
                               "--disable-features could not be kept, so nothing launches")
    return tuple(_PW_OFF)


def _disabled_in(js, where):
    """The names in js's `disabledFeatures = [...]`, None when it has none. Raises on anything in the
    list but quoted names and comments."""
    if not re.search(r"\bdisabledFeatures = \[", js):
        return None
    m = re.search(r'\bdisabledFeatures = \[((?:\s+|//[^\n]*|"\w+",?)*)\](?:\.filter\(Boolean\))?;', js)
    names = re.findall(r'"(\w+)"', re.sub(r"//[^\n]*", "", m.group(1))) if m else []
    if not names:
        raise RuntimeError(f"pw_temp: Playwright's disabledFeatures in {where} is not a plain list of names; "
                           "read it and update _disabled_in()")
    return names


def launch_args(args=None):
    """args with every --disable-features folded into one, last: Playwright's, OFF_FEATURES, the caller's."""
    feats, rest = list(playwright_disabled() + OFF_FEATURES), []
    for a in args or ():
        if a.startswith("--disable-features="):
            feats += [f for f in a.split("=", 1)[1].split(",") if f]
        else:
            rest.append(a)
    return rest + ["--disable-features=" + ",".join(dict.fromkeys(feats))]


def _wrap_launches(bt):
    """bt.launch and bt.launch_persistent_context, given launch_args(args). __wrapped__ is Playwright's."""
    for name in ("launch", "launch_persistent_context"):
        real = getattr(bt, name)

        @functools.wraps(real)
        def call(*a, _real=real, args=None, **kw):
            return _real(*a, args=launch_args(args), **kw)
        setattr(bt, name, call)


def late_close(launch, wait=8):
    """The planted late document: its request is answered only after goto has given up on it, and the
    page is closed while that navigation commits, as a tool does after a retried load. launch(pw)
    starts the browser. Returns how long pg.close() took, or None when it had not returned after
    `wait` seconds (that run's browser is then killed to release it)."""
    import http.server

    class Ok(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b"<!doctype html><p>x</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ok)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from playwright.sync_api import sync_playwright as real   # through _Run, so the kill names its folder
    run, held, closed = _Run(real), [], threading.Event()

    def release():
        if not closed.wait(wait):
            subprocess.run(["pkill", "-9", "-f", kill_pattern(run.folder)], capture_output=True)
    try:
        with run as pw:
            b = launch(pw)
            ctx = b.new_context()
            ctx.route("**/*", lambda route: held.append(route))
            pg = ctx.new_page()
            try:
                pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/", timeout=1000)
            except Exception:
                pass
            held[0].continue_()
            pg.wait_for_load_state("load", timeout=5000)
            threading.Thread(target=release, daemon=True).start()
            t = time.time()
            try:
                pg.close()
            except Exception:
                pass
            took = time.time() - t
            closed.set()
            try:
                b.close()
            except Exception:
                pass
    finally:
        srv.shutdown()
    return None if took >= wait else took


def new_folder(root=None):
    return tempfile.mkdtemp(prefix=f"{PREFIX}{os.getpid()}-", dir=root or tempfile.gettempdir())


class _Run:
    """playwright.sync_api.sync_playwright(), with the driver started on a temp folder of its own."""

    def __init__(self, real, root=None):
        self._real, self._root = real, root   # root: the selftest's own, so it never reaps the real temp dir
        self._cm = None
        self.folder = None

    def __enter__(self):
        tempfile.gettempdir()   # fix Python's own temp dir before the environment changes
        reap(self._root)
        self.folder = new_folder(self._root)
        try:
            with _env_lock:
                saved = {k: os.environ.get(k) for k in ENV_KEYS}
                os.environ.update({k: self.folder for k in ENV_KEYS})
                # The driver starts in the run's folder too, and the browser inherits its working folder
                # (Playwright passes the browser no cwd). Edge's PDF viewer writes pdf_mip_storage/ there,
                # relative: a signed-in serve run from ~/Desktop put one in the Desktop root on 2026-11-12.
                cwd = os.getcwd()
                os.chdir(self.folder)
                try:
                    self._cm = self._real()
                    pw = self._cm.__enter__()
                finally:
                    os.chdir(cwd)
                    for k, v in saved.items():
                        if v is None:
                            os.environ.pop(k, None)
                        else:
                            os.environ[k] = v
        except BaseException:
            remove(self.folder)
            raise
        _wrap_launches(pw.chromium)
        pw.stop = self.__exit__   # the real one points stop at its own __exit__
        return pw

    def start(self):
        return self.__enter__()

    def __exit__(self, *exc):
        try:
            if self._cm is not None:
                self._cm.__exit__(*exc)
        finally:
            if self.folder and os.path.lexists(self.folder):
                remove(self.folder)


def __getattr__(name):
    # `from pw_temp import sync_playwright` raises ImportError at the caller's import when Playwright is
    # missing, exactly as `from playwright.sync_api import sync_playwright` does, so the callers' own
    # `except ImportError` still reports could-not-run. reap needs no Playwright, so a tool that
    # drives a browser without it can import this module freely.
    if name == "sync_playwright":
        from playwright.sync_api import sync_playwright as real
        return lambda: _Run(real)
    raise AttributeError(name)


def selftest():
    fails, cases = [], []

    def check(label, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + label + ("" if ok else f"  ({detail})"))
        cases.append(label)
        if not ok:
            fails.append(label)

    # Planted names that no real folder can share a start with, so a pkill of one stops no real browser
    # even in a broken build: pid 999999 is above macOS's and Linux's default pid limit, and the random
    # part of a real Playwright or Chrome temp name is letters and digits, never "_".
    dead, me = 999999, os.getpid()
    # A live process standing in for another run's browser, whose folder name starts with a planted name.
    decoy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)",
                              "--user-data-dir=/x/playwright_chromiumdev_profile-_fAb123/p",
                              "--user-data-dir=/x/pw-run-999999-_aXy/q"])
    with tempfile.TemporaryDirectory() as root:
        old = time.time() - 2 * MIN_AGE
        plant = {
            f"pw-run-{dead}-_a": old, f"pw-run-{me}-_b": old, f"pw-run-{dead}-_c": time.time(),
            f"edge-run-{dead}-_d": old, "pw-run-abc-_e": old, "playwright_chromiumdev_profile-_f": old,
            "playwright-artifacts-_g": old, "playwright-artifacts-_h": old, "com.google.chrome.for.testing._i": old,
            "playwright_chromiumdev_profile-_j": time.time(), "unrelated-_k": old,
        }
        for n, t in plant.items():
            if n.startswith("com.google"):   # Chrome for Testing leaves files as well as folders
                open(os.path.join(root, n), "w").close()
            else:
                os.makedirs(os.path.join(root, n, "sub"))
            os.utime(os.path.join(root, n), (t, t))
        names = lambda paths: sorted(os.path.basename(p) for p in paths)
        dry = reap(root, dry=True)
        check("dry: names a dead pid's folders", names(dry) == [f"edge-run-{dead}-_d", f"pw-run-{dead}-_a"], names(dry))
        check("dry: deletes nothing", all(os.path.lexists(os.path.join(root, n)) for n in plant))
        gone = names(reap(root))
        check("deletes a dead pid's old folder", f"pw-run-{dead}-_a" in gone and not os.path.exists(os.path.join(root, f"pw-run-{dead}-_a")), gone)
        check("deletes a dead pid's folder under another listed prefix", f"edge-run-{dead}-_d" in gone, gone)
        check("keeps a live pid's folder", os.path.isdir(os.path.join(root, f"pw-run-{me}-_b")))
        check("keeps a dead pid's folder younger than MIN_AGE", os.path.isdir(os.path.join(root, f"pw-run-{dead}-_c")))
        check("keeps a name with no pid", os.path.isdir(os.path.join(root, "pw-run-abc-_e")))
        check("leaves legacy names alone without legacy_age", os.path.isdir(os.path.join(root, "playwright-artifacts-_g")))
        legacy = names(reap(root, legacy_age=MIN_AGE, args="... --user-data-dir=/x/playwright-artifacts-_h ..."))
        check("legacy_age: deletes old pid-less items",
              legacy == ["com.google.chrome.for.testing._i", "playwright-artifacts-_g", "playwright_chromiumdev_profile-_f"], legacy)
        check("legacy_age: keeps one a running process names", os.path.isdir(os.path.join(root, "playwright-artifacts-_h")))
        check("legacy_age: keeps a young one", os.path.isdir(os.path.join(root, "playwright_chromiumdev_profile-_j")))
        check("never touches an unrelated name", os.path.isdir(os.path.join(root, "unrelated-_k")))
        check("a live process whose folder only starts with a reaped name survives", decoy.poll() is None)
        pat = kill_pattern("/t/com.google.chrome.for.testing._i")
        check("the kill pattern matches the folder itself, dots escaped",
              re.search(pat.replace("[[:space:]]", r"\s"), "x --dir=/t/com.google.chrome.for.testing._i/a")
              and not re.search(pat.replace("[[:space:]]", r"\s"), "x --dir=/t/comXgoogle.chrome.for.testing._i/a"), pat)
    decoy.kill()

    # Windows: a pid is alive by OpenProcess and GetExitCodeProcess, never by os.kill(pid, 0), which
    # there sends CTRL_C_EVENT. A stand-in kernel32 plays each answer Windows can give.
    class Kernel32:
        def __init__(self, handle, code=STILL_ACTIVE, ok=1):
            self.handle, self.code, self.ok, self.asked, self.closed = handle, code, ok, [], []

        def OpenProcess(self, access, inherit, pid):
            self.asked.append((access, inherit, pid))
            return self.handle

        def GetExitCodeProcess(self, handle, code):
            code.contents.value = self.code
            return self.ok

        def CloseHandle(self, handle):
            self.closed.append(handle)

    k = Kernel32(8)
    check("windows: a running pid reads alive, asked with query-limited access, its handle closed",
          alive_on_windows(4242, k, lambda: 0) is True and k.asked == [(0x1000, False, 4242)] and k.closed == [8],
          (k.asked, k.closed))
    k = Kernel32(8, code=0)
    check("windows: a pid that exited reads gone, its handle closed",
          alive_on_windows(4242, k, lambda: 0) is False and k.closed == [8])
    check("windows: no handle with access denied reads alive (another user's)",
          alive_on_windows(4242, Kernel32(0), lambda: ACCESS_DENIED) is True)
    check("windows: no handle for any other reason (87, no such pid) reads gone",
          alive_on_windows(4242, Kernel32(0), lambda: 87) is False)
    check("windows: an exit code that can't be read reads gone", alive_on_windows(4242, Kernel32(8, ok=0), lambda: 0) is False)
    k = Kernel32(8)
    check("windows: pid 0 or no pid reads gone, nothing asked",
          alive_on_windows(0, k, lambda: 0) is False and alive_on_windows(None, k, lambda: 0) is False and k.asked == [])
    kills = []
    saved = (globals()["_WIN"], globals()["alive_on_windows"], os.kill)
    globals()["_WIN"], globals()["alive_on_windows"] = True, lambda pid: pid == me
    os.kill = lambda *a: kills.append(a)
    try:
        win_alive = (_alive(me), _alive(dead))
        with tempfile.TemporaryDirectory() as root:
            old = time.time() - 2 * MIN_AGE
            for n in (f"pw-run-{dead}-_a", f"pw-run-{me}-_b", "playwright-artifacts-_g"):
                os.makedirs(os.path.join(root, n))
                os.utime(os.path.join(root, n), (old, old))
            win_gone = names(reap(root, legacy_age=MIN_AGE))
    finally:
        globals()["_WIN"], globals()["alive_on_windows"] = saved[:2]
        os.kill = saved[2]
    check("windows: _alive asks alive_on_windows and never os.kill", win_alive == (True, False) and kills == [],
          (win_alive, kills))
    check("windows: reap runs there now: a gone pid's folder goes, a live one's and a legacy item stay (no ps)",
          win_gone == [f"pw-run-{dead}-_a"], win_gone)

    # Playwright's list, read from its driver; a list holding anything but names is refused.
    pw_off = playwright_disabled()
    check("the installed Playwright's disabled features are read", len(pw_off) > 5 and "HttpsUpgrades" in pw_off, pw_off)
    plain = _disabled_in('x; disabledFeatures = [\n  // why\n  "A",\n  "B"\n].filter(Boolean);', "planted")
    check("a list of names and comments is read", plain == ["A", "B"], plain)
    for what, js in (("a spread", 'disabledFeatures = ["A", ...more];'),
                     ("a conditional name", 'disabledFeatures = [on ? "A" : ""];')):
        try:
            got = _disabled_in(js, "planted")
        except RuntimeError:
            got = "refused"
        check(f"a list holding {what} is refused", got == "refused", got)

    # The wrapper, on a stub driver: the folder is in the driver's environment only while it starts,
    # Python's temp dir never moves, and the folder goes on exit, on stop() and on a failed start.
    real_tmp = tempfile.gettempdir()
    seen = {}

    class Stub:
        def __init__(self, fail=False):
            self.fail = fail

        def __enter__(self):
            seen["env"] = {k: os.environ.get(k) for k in ENV_KEYS}
            seen["cwd"] = os.getcwd()
            if self.fail:
                raise RuntimeError("driver did not start")
            pw = type("PW", (), {})()
            pw.stop = self.__exit__   # as the real one does
            pw.chromium = type("BT", (), {"launch": lambda bt, **kw: kw,
                                          "launch_persistent_context": lambda bt, d, **kw: (d, kw)})()
            return pw

        def __exit__(self, *a):
            seen["exited"] = True

    before = {k: os.environ.get(k) for k in ENV_KEYS}
    cwd0 = os.getcwd()
    with tempfile.TemporaryDirectory() as scratch:   # never the real temp dir: a broken build reaps here only
        killed = os.path.join(scratch, f"pw-run-{dead}-_z")
        os.makedirs(os.path.join(killed, "playwright_chromiumdev_profile-_z"))
        os.utime(killed, (time.time() - 2 * MIN_AGE,) * 2)
        run = _Run(Stub, scratch)
        with run as pw:
            folder = run.folder
            check("the next launch reaps a killed run's folder", not os.path.exists(killed))
            check("driver starts with every temp variable on the run's folder",
                  all(v == folder for v in seen["env"].values()), seen["env"])
            check("the folder is named for this pid", os.path.basename(folder).startswith(f"{PREFIX}{me}-"), folder)
            check("the environment is put back once the driver is up",
                  {k: os.environ.get(k) for k in ENV_KEYS} == before)
            check("the driver starts in the run's folder, so the browser's relative files (Edge's pdf_mip_storage/) "
                  "land there, and the caller's working folder is put back",
                  os.path.realpath(seen["cwd"]) == os.path.realpath(folder) and os.getcwd() == cwd0,
                  (seen["cwd"], os.getcwd()))
            check("Python's temp dir does not move", tempfile.gettempdir() == real_tmp)
            want = "--disable-features=" + ",".join(playwright_disabled() + ("RenderDocument", "Foo"))
            got = pw.chromium.launch(channel="chromium", args=["--x", "--disable-features=Foo,RenderDocument"])
            check("a launch gets one --disable-features, last: Playwright's, RenderDocument, the caller's",
                  got == {"channel": "chromium", "args": ["--x", want]}, got)
            d, kw = pw.chromium.launch_persistent_context("/p", headless=True)
            check("a persistent context keeps its folder and gets the same switch",
                  d == "/p" and kw == {"headless": True, "args": [want.replace(",Foo", "")]}, (d, kw))
            check("__wrapped__ is the driver's own launch", pw.chromium.launch.__wrapped__(args=["--y"]) == {"args": ["--y"]})
        check("the folder goes when the run ends", not os.path.exists(folder) and seen.get("exited"))
        run = _Run(Stub, scratch)
        pw = run.start()
        folder = run.folder
        pw.stop()
        check("start() then stop() deletes the folder", not os.path.exists(folder))
        run = _Run(lambda: Stub(fail=True), scratch)
        try:
            run.__enter__()
            check("a failed start raises", False)
        except RuntimeError:
            check("a failed start deletes the folder and puts the environment and the working folder back",
                  not os.path.exists(run.folder) and {k: os.environ.get(k) for k in ENV_KEYS} == before
                  and os.getcwd() == cwd0)

    print(f"\n{'PASS' if not fails else 'FAIL'}: {len(cases) - len(fails)} of {len(cases)} cases passed")
    return 1 if fails else 0


if __name__ == "__main__":
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if sys.argv[1:2] == ["reap"]:
        for p in reap(dry="--dry" in sys.argv):
            print(p)
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
