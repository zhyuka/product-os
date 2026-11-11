#!/usr/bin/env python3
"""signed_in_browser.py - one browser (Edge or Chrome) for a whole batch of steps on a signed-in site,
then gone.

    serve <url> [--minutes N] [--port P] [--channel C] [--headed]
                                           keep one signed-in browser up for several short scripts.
                                           Prints the address to connect_over_cdp to. Closes and
                                           deletes its profile after N minutes (default 90, at most
                                           240), on Ctrl-C or kill, when the window is closed, or on
                                           `stop`. Each port has its own browser and its own record.
    stop --port P                          close the browser `serve` started on port P, and check its
                                           profile is gone. No other port's browser is touched; with
                                           no --port it refuses and lists the ports up.
    status [--port P]                      which `serve` browsers are up, on which ports, until when
    selftest                               planted cases, no browser

NO WINDOW. Every launch is headless: single sign-on finishes from the Mac's saved login with no
window, measured on Outlook, Teams, SharePoint, MediaExchange and ADO. When a page needs a person (a
password, code, account picker or consent screen), the run stops at once with NEEDS SIGN-IN and exit
3, instead of opening a window mid-work; the calling session asks for the sign-in once, through its
contact session, and only then runs `serve ... --headed` (or sets SIGNED_IN_BROWSER_HEADED=1 for a
`session`), the one launch that shows a window.

In Python, for a batch that runs in one process:

    with signed_in_browser.session(url, ready=check) as s:
        ... s.page ... s.goto(next_url) ...

WHY. A tool that launches a fresh browser for every step pays a sign-in each time, and a browser with
force-installed extensions can unpack hundreds of MB per launch. A tool that keeps its signed-in
profile for reuse leaves session cookies on disk. Every tool that drives a signed-in site gets its
browser here instead, once per batch, and the profile goes when the batch ends.

CONFIG (product-os config, all optional):
    signed_in_browser.channel            "msedge" (default) or "chrome": the installed browser to drive
    signed_in_browser.sign_in_buttons    {"<host>": "<regex>"}: a site's own landing page in front of
                                         single sign-on, and the name of its one sign-in button
    signed_in_browser.account            the user's own address: the one tile it may click on
                                         Microsoft's account picker (unset: it clicks none)
    signed_in_browser.no_profile_under   folders a profile must never sit under, because they are
                                         synced to a cloud drive or backed up (default ~/Desktop and
                                         ~/Documents)
--channel on the command line overrides the config.

RULES IT KEEPS
  - The profile is a fresh folder in the system temp dir, never under a synced folder. It refuses to
    start when the temp dir resolves under one. No signed-in profile is kept between sessions: the
    folder is deleted when the batch ends, and a run that was killed is reaped at the next launch,
    by its pid in the folder's name.
  - `serve` has a hard limit (default 90 minutes, at most 240) so a forgotten browser does not
    outlive the session that needed it.
  - The browser's temp files go inside the same folder (MAC_CHROMIUM_TMPDIR), so they go with it.
  - It types nothing into any page. Signing in is the caller's `ready` function. `sso_ready` here
    only waits while single sign-on finishes on its own. On a password, code, account picker or
    consent screen a headless run stops with NEEDS SIGN-IN; a `--headed` run hands the window to the
    user.
  - No launch shows a window unless the run asked for one (`--headed`, headed=True or
    SIGNED_IN_BROWSER_HEADED=1); `launch_refusal` checks the final launch options, so an edit that
    turns the window back on fails there and in the selftest.
  - `serve` keeps one record per port (signed_in_serve_<port>.json in the temp dir), taken before
    the browser starts, so two `serve`s on one port can't both start and `stop` on one port leaves
    the others alone. It refuses a port something else already listens on, naming a free one.
  - On a site with a landing page of its own (config sign_in_buttons), `sso_ready` clicks that
    page's one sign-in button so single sign-on starts; a click on a button, never a field.
  - On Microsoft's account picker `sso_ready` clicks the user's own tile (config account), once a
    run, and only on login.microsoftonline.com or login.microsoft.com, with no password or code field
    on the page, when the picker lists exactly one account and it is that address. Never "Use
    another account". Whatever comes after the click ends the run with NEEDS SIGN-IN.

EXIT 0 done, 1 refused, 2 did not run (no Playwright or browser, single sign-on did not finish),
3 needs sign-in (a person has to act; nothing was typed and no window opened).

BLIND TO what the steps do; it counts launches (LAUNCHES), it does not check them. A `serve` browser
answers any local process on its port while it is up. A folder reaped by pid could in principle
belong to a new process that reused the pid; it is then only reaped later. A headless window is
not drawn, but macOS still lists it, off the bottom of the screen.
"""
import os
import sys
# Run through a symlink, Windows leaves the link's folder first on sys.path (POSIX resolves it): take this file's own.
if __name__ == "__main__" and sys.path and os.path.normcase(sys.path[0]) == os.path.normcase(os.path.dirname(__file__)):
    sys.path[0] = os.path.dirname(os.path.realpath(__file__))
import contextlib, json, os, re, shutil, signal, sys, tempfile, time, urllib.parse

if os.path.dirname(os.path.realpath(__file__)) not in sys.path: sys.path.append(os.path.dirname(os.path.realpath(__file__)))
try:
    import kit_config
except ImportError:
    kit_config = None

PREFIX = "signed_in_"          # folder name: signed_in_<pid>_<random>
SERVE_DEFAULT, SERVE_MAX = 90, 240
SERVE_PORT = 9333
LAUNCHES = 0                   # browser launches in this process; the selftests and batch callers read it
NEEDS_SIGN_IN = "needs sign-in"   # a reason that starts so is a person's step, not a failure
HEADED_ENV = "SIGNED_IN_BROWSER_HEADED"
_HEADED = False                # whether this process's last launch has a window
_WIN = os.name == "nt"         # Windows: liveness, the serve's signals, stop and Edge's temp dir differ
STOP_FILE = "stop"             # Windows: `stop` writes it in the serve's folder, and the serve closes itself
# Sites whose sign-in lands on another host: Microsoft 365 moved its apps to cloud.microsoft
# (measured 2026-11-10: outlook.office.com ends on outlook.cloud.microsoft, teams.microsoft.com on
# teams.cloud.microsoft). Without these the page is signed in but never counts as on the site.
MOVED = {"outlook.office.com": ("outlook.cloud.microsoft",),
         "outlook.office365.com": ("outlook.cloud.microsoft",),
         "teams.microsoft.com": ("teams.cloud.microsoft",)}


def _cfg(key, default):
    v = kit_config.get("signed_in_browser", key) if kit_config else None
    return default if v in (None, "", []) else v


def channel():
    return _cfg("channel", "msedge")


def account():
    """The user's own address (config signed_in_browser.account), for Microsoft's account picker;
    '' when unset, and then no tile is ever clicked."""
    a = _cfg("account", "")
    a = a.strip().lower() if isinstance(a, str) else ""
    return a if re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", a) else ""


def sign_in_buttons():
    """{host: regex} from config: sites with a landing page of their own in front of single
    sign-on, and the one button that starts it. Without the click a signed-out landing counts as
    ready."""
    v = _cfg("sign_in_buttons", {})
    return v if isinstance(v, dict) else {}


def no_profile_under():
    roots = _cfg("no_profile_under", ["~/Desktop", "~/Documents"])
    return [os.path.realpath(os.path.expanduser(r)) for r in roots]


def temp_root():
    """The per-user temp dir. On macOS read from the system, so a scheduled job without TMPDIR (which
    falls back to /tmp) looks where a shell's run put the profile."""
    if sys.platform == "darwin":
        try:
            import subprocess
            d = subprocess.run(["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True,
                               timeout=20).stdout.strip()
            if d and os.path.isdir(d):
                return os.path.realpath(d)
        except (OSError, subprocess.SubprocessError):
            pass
    return os.path.realpath(tempfile.gettempdir())


STATE_ROOT = temp_root()
LEGACY_STATE = "signed_in_serve.json"   # the one record every port shared before 11-10; read, never written


def state_path(port, root=None):
    """The record of the `serve` on this port. One file per port, so ports never share a record."""
    return os.path.join(root or STATE_ROOT, f"signed_in_serve_{int(port)}.json")


def headed():
    """Whether this process's last launch has a window a person can act in. A caller's own sign-in
    loop reads it to stop with NEEDS_SIGN_IN instead of waiting on a window nobody can see."""
    return _HEADED


def asked_for_window(asked=False):
    """A launch shows a window only when the run asked: headed=True, `--headed`, or HEADED_ENV=1,
    each set for a launch where a person signs in, or by a caller whose site refuses a headless
    browser (figma_attach on figma.com, with its config's figma.window)."""
    return bool(asked) or os.environ.get(HEADED_ENV) == "1"


def root_refusal(root, synced=None):
    """Refusal text or None: the profile must not sit under a synced folder."""
    real = os.path.realpath(root)
    for s in (no_profile_under() if synced is None else [os.path.realpath(x) for x in synced]):
        if real == s or real.startswith(s + os.sep):
            return (f"REFUSED: the temp dir {real} is under {s}, which is synced or backed up; a "
                    "signed-in profile may not go there. Unset TMPDIR or point it elsewhere.")
    return None


def _alive(pid):
    """Whether pid is a running process. A zombie (exited, its parent not yet told) is not: `stop`
    would otherwise wait out its whole limit on a serve that already closed. Neither is a record's
    missing pid (0, which would signal this process group). On Windows os.kill(pid, 0) sends
    CTRL_C_EVENT and reads every pid alive, so pw_temp.alive_on_windows asks instead."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if _WIN:
        import pw_temp
        return pw_temp.alive_on_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (TypeError, ValueError, OverflowError):
        return False
    if os.name != "nt":
        try:
            import subprocess
            st = subprocess.run(["ps", "-o", "stat=", "-p", str(int(pid))], capture_output=True,
                                text=True, timeout=10).stdout.strip()
            if st.startswith("Z"):
                return False
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return True


def reap(root=None, now=None, alive=_alive, dry=False):
    """Delete profile folders left by runs that were killed (their pid is gone). Returns the paths
    deleted (with dry, the ones it would delete). Runs at every launch, and daily from upkeep.py."""
    root = root or temp_root()
    gone = []
    try:
        names = os.listdir(root)
    except OSError:
        return gone
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        m = re.match(re.escape(PREFIX) + r"(\d+)_", name)
        if not m:
            continue
        pid = int(m.group(1))
        if pid == os.getpid() or alive(pid):
            continue
        if dry:
            gone.append(path)
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            gone.append(path)
    if not dry and root == temp_root():
        for path in _state_files(STATE_ROOT):
            st = _read_state(path)
            if st is not None and not _alive(st.get("pid", 0)) and not os.path.exists(st.get("folder") or ""):
                try:
                    os.remove(path)   # a killed serve's record, its folder already reaped
                except OSError:
                    pass
    return gone


def new_folder(root=None, synced=None):
    root = root or temp_root()
    why = root_refusal(root, synced)
    if why:
        raise SystemExit(why)
    return tempfile.mkdtemp(prefix=f"{PREFIX}{os.getpid()}_", dir=root)


def sso_ready(host):
    """A `ready` function for a site on `host` behind single sign-on: 'ready' once the tab is on that
    host with content and no sign-in form, 'needs-user' on a password, code, account picker or
    consent screen, or an identity provider's email field, else 'wait'. It never types."""
    js = """() => ({url: location.href,
      password: !!document.querySelector('input[type=password]'),
      code: !!document.querySelector('input[autocomplete="one-time-code"],input[name=otc]'),
      email: !!document.querySelector('input[type=email],input[name=loginfmt],input[name=identifier]'),
      text: document.body ? document.body.innerText.slice(0, 3000) : ''})"""

    pattern, clicks = sign_in_buttons().get(host), {"n": 0}
    mine, picked = account(), {"n": 0}

    def ready(page):
        try:
            info = page.evaluate(js)
        except Exception:
            return "wait"
        state = classify(info, host)
        if state == "ready" and pattern:
            return press_sign_in(page, pattern, clicks)
        if state == "needs-user" and pick_account(page, mine, picked):
            return "wait"
        return state
    return ready


# Microsoft's account picker ("Pick an account"). Each account is a tile button whose data-test-id
# is its address; "Use another account" (#otherTile) and a tile's menu (<address>-menu-dots) are not.
PICKER_HOSTS = ("login.microsoftonline.com", "login.microsoft.com")
TILES_JS = """() => ({
  picker: /pick an account/i.test(document.body ? document.body.innerText : ''),
  password: !!document.querySelector('input[type=password]'),
  code: !!document.querySelector('input[autocomplete="one-time-code"],input[name=otc]'),
  tiles: [...document.querySelectorAll('#tilesHolder [role=button][data-test-id]')]
           .map(e => e.getAttribute('data-test-id') || '')
           .filter(t => t.includes('@') && !t.endsWith('-menu-dots'))})"""


def tile_to_pick(info, url, mine):
    """The one tile this run may click on Microsoft's account picker, or None. Only on Microsoft's own
    sign-in host, with no password or code field, when the picker shows exactly one account and it is
    the user's own address. Two accounts, another address, or no address configured: None."""
    if not mine or urllib.parse.urlparse(url or "").netloc not in PICKER_HOSTS:
        return None
    if not info.get("picker") or info.get("password") or info.get("code"):
        return None
    tiles = [str(t).strip().lower() for t in info.get("tiles") or []]
    return tiles[0] if tiles == [mine] else None


def pick_account(page, mine, picked):
    """Click the user's own tile on Microsoft's account picker when tile_to_pick allows it, at most
    once a run, so whatever comes after the click (a password, MFA, consent, the picker again) ends
    the run with NEEDS SIGN-IN. A click on a tile, never a field. True when it clicked."""
    if picked["n"] or not mine:
        return False
    try:
        addr = tile_to_pick(page.evaluate(TILES_JS), page.url, mine)
        if not addr:
            return False
        picked["n"] += 1
        page.locator(f'#tilesHolder [role=button][data-test-id="{addr}"]').click(timeout=10000)
    except Exception:
        return False
    print("  account picker: clicked the one account tile, the configured address; nothing typed", flush=True)
    return True


def press_sign_in(page, pattern, clicks, most=2):
    """On a site's own landing page: 'ready' once its sign-in button is gone, else click the button
    (a button, never a field; at most `most` times) and 'wait' while single sign-on starts."""
    try:
        rx = re.compile(pattern, re.I)
        btn = page.get_by_role("button", name=rx)
        if not btn.count():
            btn = page.get_by_role("link", name=rx)
        if not btn.count():
            return "ready"
        if clicks["n"] >= most:
            return "wait"            # the landing stays; the settle time ends the run
        btn.first.click(timeout=10000)
        clicks["n"] += 1
        return "wait"
    except Exception:
        return "wait"


def classify(info, host):
    at = urllib.parse.urlparse(info.get("url") or "").netloc
    on_site = any(at == h or at.endswith("." + h) for h in (host, *MOVED.get(host, ())))
    if info.get("password") or info.get("code"):
        return "needs-user"
    # The picker and consent words count only off the site: on it they are a mail or a page that
    # mentions them, and a headless run would stop for a sign-in nobody needs.
    if not on_site and re.search(r"pick an account|choose an account|permissions requested|consent",
                                 info.get("text") or "", re.I):
        return "needs-user"
    if not on_site and info.get("email"):
        return "needs-user"      # the identity provider asks who you are: the user's to answer
    if on_site:
        return "ready" if len(info.get("text") or "") > 200 else "wait"
    return "wait"


def _page_host(page):
    try:
        return urllib.parse.urlparse(page.url).netloc or "a blank page"
    except Exception:
        return "an unknown page"


def wait_ready(page, ready, wait_user, settle=90, now=time.time, sleep=time.sleep, window=None,
               stopped=lambda: False):
    """Poll ready(page) until 'ready'. 'ready', or why not.
    With no window (the default; `window` None reads this process's launch): on 'needs-user' it
    returns NEEDS_SIGN_IN at once, and after `settle` seconds of waiting it gives up, since nobody
    can see the page. With a window, after `settle` seconds or at once on 'needs-user', the window is
    the user's for `wait_user` seconds. 'stopped' as soon as stopped() is true (serve's stop)."""
    window = headed() if window is None else window
    start, user_since = now(), None
    while True:
        if stopped():
            return "stopped"
        state = ready(page)
        if state == "ready":
            return "ready"
        if state not in ("wait", "needs-user"):
            return state             # the caller's own reason
        if not window and state == "needs-user":
            return (f"{NEEDS_SIGN_IN}: {_page_host(page)} asks for a person (a password, code, account "
                    "picker or consent screen). Nothing was typed and no window opened")
        if not window and now() - start > settle:
            return f"single sign-on did not finish within {settle}s (last at {_page_host(page)})"
        if user_since is None and (state == "needs-user" or now() - start > settle):
            user_since = now()
            print(f"  SIGN-IN NEEDS YOU: finish it in the browser window that opened. Waiting {wait_user}s.")
        if user_since is not None and now() - user_since > wait_user:
            return f"the sign-in was not finished within {wait_user}s"
        sleep(1)


class Session:
    def __init__(self, page, ctx, folder):
        self.page, self.ctx, self.folder = page, ctx, folder

    def goto(self, url, timeout=90000):
        """Open url, once more if the first load after idle drops the connection."""
        from playwright.sync_api import Error as PlaywrightError
        for attempt in (1, 2):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                return
            except PlaywrightError:
                if attempt == 2:
                    raise


class NotReady(Exception):
    """The browser or the sign-in did not get far enough; str() says why."""


class NeedsSignIn(NotReady):
    """A person has to sign in. Nothing was typed and no window opened; ask once, then rerun headed."""


def launch_options(folder, args=(), chan=None, window=False):
    """The options the browser starts with. Headless unless the run asked for a window. A site's
    permission request (notifications, camera, location) is denied, never shown: headless denies it
    on its own (measured), and --deny-permission-prompts does the same for a --headed launch. The
    browser's own temp files go in the folder too: Chromium reads MAC_CHROMIUM_TMPDIR on macOS, and
    TMP, then TEMP, on Windows."""
    env = dict(os.environ, MAC_CHROMIUM_TMPDIR=os.path.join(folder, "t"))
    if _WIN:
        env.update(TMP=env["MAC_CHROMIUM_TMPDIR"], TEMP=env["MAC_CHROMIUM_TMPDIR"])
    return dict(user_data_dir=os.path.join(folder, "profile"), channel=chan or channel(),
                headless=not window, env=env, viewport={"width": 1280, "height": 900},
                args=["--no-first-run", "--no-default-browser-check", "--deny-permission-prompts", *args])


def launch_refusal(opts, window):
    """Refusal text or None: a launch that would show a window the run did not ask for."""
    shows = opts.get("headless") is False or any(
        str(a).startswith("--headless=false") for a in opts.get("args") or ())
    if shows and not window:
        return ("REFUSED: this launch would open a browser window, and the run did not ask for one. "
                "Launches are headless; only a person's sign-in (--headed, headed=True or "
                f"{HEADED_ENV}=1) shows a window.")
    return None


def _launch(p, folder, args=(), chan=None, window=False):
    """Start the browser on the folder's profile, headless unless `window`. The playwright handle
    `p` is the caller's. Raises NotReady, before starting anything, on a window nobody asked for."""
    global LAUNCHES, _HEADED
    opts = launch_options(folder, args, chan, window)
    why = launch_refusal(opts, window)
    if why:
        raise NotReady(why)
    os.makedirs(opts["env"]["MAC_CHROMIUM_TMPDIR"], exist_ok=True)
    LAUNCHES += 1
    _HEADED = not opts["headless"]
    return p.chromium.launch_persistent_context(opts.pop("user_data_dir"), **opts)


@contextlib.contextmanager
def session(url, ready=None, wait_user=180, chan=None, headed=False):
    """One browser for the whole `with` block: launched once, `url` opened, `ready(page)` waited for,
    then closed and its profile deleted however the block ends. Headless unless `headed` (or
    HEADED_ENV=1). Raises NeedsSignIn when a person has to sign in, and NotReady when the browser did
    not start, `url` did not load, or the sign-in was not finished."""
    window = asked_for_window(headed)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from pw_temp import sync_playwright   # the driver's own temp folder goes with the run too
    except ImportError:
        raise NotReady("Playwright is not installed for this Python (pip install playwright)")
    reap()
    folder = new_folder()
    try:
        with sync_playwright() as p:
            try:
                ctx = _launch(p, folder, chan=chan, window=window)
            except PlaywrightError as e:
                raise NotReady(f"the browser did not start: {str(e).splitlines()[0]}")
            try:
                pg = ctx.pages[0] if ctx.pages else ctx.new_page()
                s = Session(pg, ctx, folder)
                try:
                    s.goto(url)
                except PlaywrightError as e:
                    raise NotReady(f"{url[:60]} did not load: {str(e).splitlines()[0]}")
                if ready is not None:
                    state = wait_ready(pg, ready, wait_user, window=window)
                    if state != "ready":
                        raise (NeedsSignIn if str(state).startswith(NEEDS_SIGN_IN) else NotReady)(state)
                yield s
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)   # the profile held the session cookies


# --- serve: one browser for several scripts, with a hard limit ----------------------------------

def _state_files(root=None):
    """Every serve record in the temp dir: one per port, and the shared one older runs still write."""
    root = root or STATE_ROOT
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    return [os.path.join(root, n) for n in names
            if n == LEGACY_STATE or re.fullmatch(r"signed_in_serve_\d+\.json", n)]


def _read_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_state(path, d):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".signed_in_serve_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def record_for(port, root=None):
    """(path, record) of the serve on this port, or (None, None). An older run's shared record
    counts when it names this port, so `stop --port` reaches a browser started before the split."""
    path = state_path(port, root)
    st = _read_state(path)
    if st is not None:
        return path, st
    legacy = os.path.join(root or STATE_ROOT, LEGACY_STATE)
    st = _read_state(legacy)
    if st is not None and int(st.get("port") or 0) == int(port):
        return legacy, st
    return None, None


def claim(port, rec, root=None, alive=_alive, now=time.time):
    """Take the port's record before the browser starts. None when this run took it, else the live
    record that holds the port. The file is created exclusively, so of two serves racing for one port only one
    gets it; a dead serve's record is taken over."""
    path = state_path(port, root)
    for _ in range(3):
        _, old = record_for(port, root)
        if old is not None and alive(old.get("pid", 0)):
            return old
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Another serve may have taken the port since the check above: read it again.
            cur = _read_state(path)
            if cur is not None and alive(cur.get("pid", 0)):
                return cur
            if cur is None:
                try:
                    if now() - os.path.getmtime(path) < 30:
                        return {"pid": "unknown (its record is being written)", "port": port}
                except OSError:
                    continue
            try:
                os.remove(path)          # a dead serve's record, or one left unreadable
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f)
            f.flush()
            os.fsync(f.fileno())
        return None
    return {"pid": "unknown", "port": port}


def release(port, pid=None, root=None):
    """Remove the port's record if it is this process's (or pid's)."""
    path = state_path(port, root)
    st = _read_state(path)
    if st is not None and st.get("pid") == (pid or os.getpid()):
        try:
            os.remove(path)
        except OSError:
            pass


def port_in_use(port):
    import socket
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", int(port))) == 0


def free_port(start=SERVE_PORT, count=30, root=None, alive=_alive, in_use=port_in_use):
    """The first port from `start` with no live serve record and nothing listening, or None."""
    for p in range(start, start + count):
        _, st = record_for(p, root)
        if (st is None or not alive(st.get("pid", 0))) and not in_use(p):
            return p
    return None


def _until(st):
    return time.strftime('%H:%M', time.localtime(st.get("deadline") or 0))


def serve(url, minutes=SERVE_DEFAULT, port=SERVE_PORT, wait_user=600, chan=None, headed=False):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from pw_temp import sync_playwright
    except ImportError:
        print("DID NOT RUN: Playwright is not installed for this Python (pip install playwright).")
        return 2
    minutes = max(1, min(int(minutes), SERVE_MAX))
    window = asked_for_window(headed)
    rec = {"pid": os.getpid(), "port": port, "folder": "", "url": url, "started": time.time(),
           "deadline": time.time() + minutes * 60, "window": window}
    held = claim(port, rec)
    if held:
        free = free_port()
        print(f"REFUSED: a serve browser is already up on port {port} (pid {held.get('pid')}, until "
              f"{_until(held)}), maybe another session's; leave it. Serve on a free port"
              + (f": --port {free}." if free else "."))
        return 1
    folder, why, code = "", "did not start", 0
    try:
        if port_in_use(port):
            free = free_port()
            print(f"REFUSED: something other than a serve browser already listens on port {port}; "
                  "serve on a free port" + (f": --port {free}." if free else "."))
            return 1
        reap()
        folder = new_folder()
        stop = {"now": False}
        for sig in _stop_signals():
            signal.signal(sig, lambda *_: stop.update(now=True))
        if _WIN:
            _watch_stop_file(folder, stop)
        host = urllib.parse.urlparse(url).netloc
        _write_state(state_path(port), dict(rec, folder=folder))
        with sync_playwright() as p:
            try:
                ctx = _launch(p, folder, [f"--remote-debugging-port={port}"], chan, window)
            except PlaywrightError as e:
                print(f"DID NOT RUN: the browser did not start: {str(e).splitlines()[0]}")
                return 2
            except NotReady as e:
                print(e)
                return 1
            closed = {"yes": False}
            ctx.on("close", lambda *_: closed.update(yes=True))
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                Session(pg, ctx, folder).goto(url)
            except PlaywrightError as e:
                print(f"DID NOT RUN: {url[:60]} did not load: {str(e).splitlines()[0]}")
                ctx.close()
                return 2
            deadline = time.time() + minutes * 60
            _write_state(state_path(port), dict(rec, folder=folder, deadline=deadline))
            state = wait_ready(pg, sso_ready(host), wait_user, window=window, stopped=lambda: stop["now"] or closed["yes"])
            if state == "stopped":
                why = "stopped" if stop["now"] else "the browser closed"
                why += " while it waited for single sign-on"
            elif state != "ready" and not window:
                code = 3 if state.startswith(NEEDS_SIGN_IN) else 2
                detail = state[len(NEEDS_SIGN_IN) + 2:] if code == 3 else state
                print(f"{'NEEDS SIGN-IN' if code == 3 else 'DID NOT RUN'}: {detail}.", flush=True)
                if code == 3:
                    print("  Ask for the sign-in once, through your contact session, then run "
                          f"`serve {url} --port {port} --headed`: the one launch that shows a window.")
                why = "needs sign-in" if code == 3 else "single sign-on did not finish"
            else:
                print(f"SERVING http://127.0.0.1:{port} ({state}, {'with a window' if window else 'headless'}) "
                      f"until {time.strftime('%H:%M', time.localtime(deadline))}. Connect with playwright "
                      "chromium.connect_over_cdp; never call browser.close() there. Close it with "
                      f"`stop --port {port}`.", flush=True)
                while not stop["now"] and not closed["yes"] and time.time() < deadline:
                    try:
                        pg.wait_for_timeout(1000)
                    except PlaywrightError:
                        break              # the window or the tab was closed
                why = ("stopped" if stop["now"] else "the browser closed" if closed["yes"]
                       else f"{minutes} minutes up")
            try:
                ctx.close()
            except Exception:
                pass
    finally:
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
        release(port)
    print(f"CLOSED ({why}); profile deleted: {not os.path.exists(folder)}")
    return code


def _stop_signals(mod=signal):
    """The signals that stop a serve: SIGTERM, SIGINT and SIGHUP, and on Windows, which has no SIGHUP,
    SIGTERM, SIGINT and SIGBREAK (Ctrl+Break)."""
    return [getattr(mod, n) for n in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK") if hasattr(mod, n)]


def _watch_stop_file(folder, stop, interval=0.5):
    """Windows: set stop["now"] once `stop` writes STOP_FILE in the serve's folder, so the serve closes
    the browser and deletes its profile itself. There is no SIGTERM to send there: os.kill ends the
    one process at once, before its cleanup, and leaves its driver and Edge running."""
    import threading
    path = os.path.join(folder, STOP_FILE)

    def watch():
        while not stop["now"]:
            if os.path.exists(path):
                stop["now"] = True
                return
            time.sleep(interval)

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    return t


def _kill_tree(pid):
    """Windows: end pid and every process under it, its driver and Edge too (taskkill /T /F)."""
    import subprocess
    try:
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, timeout=60)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass


def stop_serve(port=None, wait=90, root=None, alive=_alive, kill_tree=None):   # a loaded machine can take well over 30 s to close the browser
    up = [f"{s.get('port')} (pid {s.get('pid')})" for s in map(_read_state, _state_files(root))
          if s and alive(s.get("pid", 0)) and (port is None or int(s.get("port") or 0) != int(port))]
    if port is None:
        print("REFUSED: say which serve to stop, `stop --port P`, the port your own `serve` printed; "
              "another session's browser may be on any of them." + (f" Up: {', '.join(up)}." if up else ""))
        return 1
    path, st = record_for(port, root)
    if not st:
        print(f"Nothing to stop: no serve browser is recorded on port {port}."
              + (f" Up on other ports, left alone: {', '.join(up)}." if up else ""))
        return 0
    pid, folder = st.get("pid", 0), st.get("folder", "")
    if alive(pid):
        asked = False
        if _WIN and folder and os.path.isdir(folder):   # the serve closes itself (_watch_stop_file)
            try:
                open(os.path.join(folder, STOP_FILE), "w").close()
                asked = True
            except OSError:
                pass
        elif not _WIN:
            os.kill(pid, signal.SIGTERM)
            asked = True
        for _ in range(wait if asked else 0):
            if not alive(pid):
                break
            time.sleep(1)
        if _WIN and alive(pid):
            (kill_tree or _kill_tree)(pid)
            for _ in range(10):
                if not alive(pid):
                    break
                time.sleep(1)
    if alive(pid):
        print(f"DID NOT RUN: pid {pid} is still up after {wait}s.")
        return 2
    if folder and os.path.exists(folder):
        shutil.rmtree(folder, ignore_errors=True)
    st2 = _read_state(path)
    if st2 is not None and st2.get("pid") == pid:
        os.remove(path)
    print(f"Stopped pid {pid} on port {port}; profile folder gone: {not os.path.exists(folder)}")
    return 0


def status(port=None, root=None):
    seen = []
    for path in _state_files(root):
        st = _read_state(path)
        if not st or not _alive(st.get("pid", 0)) or (port is not None and int(st.get("port") or 0) != int(port)):
            continue
        seen.append(st)
        mode = "with a window" if st.get("window", True) else "headless"
        print(f"Serve browser up: pid {st['pid']}, http://127.0.0.1:{st['port']}, {mode}, {st['url'][:60]}, "
              f"until {_until(st)}.")
    if not seen:
        print("No serve browser is up" + (f" on port {port}." if port is not None else "."))
    return 0


def selftest():
    results = []

    def case(name, ok):
        results.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    td = tempfile.mkdtemp(prefix="sib-selftest-")
    try:
        live, dead = os.path.join(td, f"{PREFIX}111_a"), os.path.join(td, f"{PREFIX}222_b")
        other = os.path.join(td, "playwright_chromiumdev_profile-z")
        for d in (live, dead, other):
            os.makedirs(os.path.join(d, "profile"))
        would = reap(td, alive=lambda pid: pid == 111, dry=True)
        case("reap --dry: names the dead pid's folder, deletes nothing",
             would == [dead] and os.path.exists(dead))
        gone = reap(td, alive=lambda pid: pid == 111)
        case("reap: a profile whose pid is gone is deleted", dead in gone and not os.path.exists(dead))
        case("reap: a profile whose pid is alive is kept", os.path.exists(live))
        case("reap: a folder no tool of ours made is kept", os.path.exists(other))
        synced = os.path.join(td, "Synced")
        case("a temp dir under a synced folder is refused", root_refusal(os.path.join(synced, "x"), [synced]) is not None)
        case("... and the synced folder itself", root_refusal(synced, [synced]) is not None)
        case("a sibling whose name only starts the same passes", root_refusal(synced + "-other", [synced]) is None)
        case("the default list holds the home Desktop", os.path.realpath(os.path.expanduser("~/Desktop"))
             in no_profile_under() or kit_config and kit_config.get("signed_in_browser", "no_profile_under"))
        f = new_folder(td, [])
        case("a new profile folder carries this pid", os.path.basename(f).startswith(f"{PREFIX}{os.getpid()}_"))
        case("... and reap leaves this process's own folder alone", f not in reap(td) and os.path.exists(f))
        site = "app.example.com"
        case("on the site with content: ready",
             classify({"url": "https://app.example.com/home", "text": "x" * 300}, site) == "ready")
        case("on the site, still blank: wait",
             classify({"url": "https://app.example.com/home", "text": ""}, site) == "wait")
        case("a blank redirect through the identity provider: wait",
             classify({"url": "https://idp.example.net/saml2", "text": ""}, site) == "wait")
        case("the identity provider's account field: the user's, never typed into",
             classify({"url": "https://idp.example.net/x", "email": True}, site) == "needs-user")
        case("a password: the user's",
             classify({"url": "https://idp.example.net/x", "password": True}, site) == "needs-user")
        case("an account picker: the user's",
             classify({"url": "https://idp.example.net/x", "text": "Pick an account"}, site) == "needs-user")
        case("a look-alike host is not the site",
             classify({"url": "https://app.example.com.evil.example/", "text": "x" * 300}, site) == "wait")
        clock = [0.0]
        tick = lambda: clock[0]

        def sleep(_):
            clock[0] += 1
        states = iter(["wait", "wait", "ready"])
        case("wait_ready: waits out the redirect and reports ready",
             wait_ready(None, lambda _: next(states), 5, now=tick, sleep=sleep) == "ready")
        clock[0] = 0.0
        got = wait_ready(None, lambda _: "needs-user", 3, now=tick, sleep=sleep, window=True)
        case("wait_ready with a window: a sign-in the user never finishes gives up after the user's wait",
             "not finished" in got)
        case("wait_ready: a caller's own reason comes back as is",
             wait_ready(None, lambda _: "the account is someone else's", 3, now=tick, sleep=sleep)
             == "the account is someone else's")
        clock[0] = 0.0
        got = wait_ready(None, lambda _: "needs-user", 600, now=tick, sleep=sleep, window=False)
        case("headless: a sign-in screen stops at once with NEEDS SIGN-IN, waiting on nobody",
             got.startswith(NEEDS_SIGN_IN) and clock[0] == 0)
        clock[0] = 0.0
        got = wait_ready(None, lambda _: "wait", 600, settle=5, now=tick, sleep=sleep, window=False)
        case("headless: a sign-on that never lands gives up after the settle time, not the user's wait",
             "did not finish" in got and not got.startswith(NEEDS_SIGN_IN) and clock[0] < 10)
        case("Outlook signed in on its new host counts as the site", classify(
            {"url": "https://outlook.cloud.microsoft/mail/", "text": "x" * 300}, "outlook.office.com") == "ready")
        case("Teams signed in on its new host counts as the site", classify(
            {"url": "https://teams.cloud.microsoft/v2/", "text": "x" * 300}, "teams.microsoft.com") == "ready")
        case("a look-alike of the new host is not the site", classify(
            {"url": "https://outlook.cloud.microsoft.evil.example/", "text": "x" * 300}, "outlook.office.com") == "wait")
        case("a mail on the site that says 'consent' is not a consent screen", classify(
            {"url": "https://app.example.com/mail", "text": "Please give consent. " + "x" * 300}, site) == "ready")

        # A site's own landing page: its sign-in button is clicked, at most twice, never a field.
        class Landing:
            def __init__(self, shows):
                self.shows, self.clicks = list(shows), 0

            def get_by_role(self, role, name=None):
                page, here = self, bool(self.shows and self.shows[0]) and role == "button"

                class Loc:
                    first = property(lambda s: s)

                    def count(s):
                        return int(here and bool(name.search("Sign in with Microsoft Entra")))

                    def click(s, timeout=None):
                        page.clicks += 1
                return Loc()
        pg = Landing([True])
        n = {"n": 0}
        first = press_sign_in(pg, r"Sign in with Microsoft Entra", n)
        pg.shows = [False]
        case("a site's landing: its sign-in button is clicked once, then the page counts once it is gone",
             first == "wait" and pg.clicks == 1 and press_sign_in(pg, r"Sign in with Microsoft Entra", n) == "ready")
        pg, n = Landing([True]), {"n": 0}
        got = [press_sign_in(pg, r"Sign in with Microsoft Entra", n) for _ in range(4)]
        case("... and a landing that stays is clicked at most twice", pg.clicks == 2 and got == ["wait"] * 4)
        case("a button that is not the site's own sign-in button is not clicked",
             press_sign_in(Landing([True]), r"^Log in$", {"n": 0}) == "ready")

        # Microsoft's account picker: the user's own tile, only under every guard, once a run.
        mine_addr = "pat@example.com"
        picker_url = "https://login.microsoftonline.com/t/oauth2/v2.0/authorize"
        one = {"picker": True, "tiles": [mine_addr]}
        case("the picker lists one account, the user's own: that tile", tile_to_pick(one, picker_url, mine_addr) == mine_addr)
        case("... on login.microsoft.com too", tile_to_pick(one, "https://login.microsoft.com/c/x", mine_addr) == mine_addr)
        case("two accounts (the user's and another tenant's): no tile, the user picks", tile_to_pick(
            {"picker": True, "tiles": [mine_addr, "pat@dev.example.com"]}, picker_url, mine_addr) is None)
        case("one account that is not the user's: no tile",
             tile_to_pick({"picker": True, "tiles": ["sam@example.com"]}, picker_url, mine_addr) is None)
        case("a password field on the page: no tile", tile_to_pick(dict(one, password=True), picker_url, mine_addr) is None)
        case("a code field on the page: no tile", tile_to_pick(dict(one, code=True), picker_url, mine_addr) is None)
        case("a look-alike of Microsoft's host: no tile",
             tile_to_pick(one, "https://login.microsoftonline.com.evil.example/x", mine_addr) is None)
        case("a page that is not the picker: no tile", tile_to_pick(dict(one, picker=False), picker_url, mine_addr) is None)
        case("only 'Use another account' left: no tile", tile_to_pick({"picker": True, "tiles": []}, picker_url, mine_addr) is None)
        case("no address configured (the default): no tile", tile_to_pick(one, picker_url, "") is None and account() == "")

        class PickerPage:
            url = picker_url

            def __init__(self):
                self.clicked = []

            def evaluate(self, js):
                return dict(one, url=picker_url, text="Pick an account")

            def locator(self, sel):
                page = self

                class L:
                    def click(s, timeout=None):
                        page.clicked.append(sel)
                return L()
        pp, once = PickerPage(), {"n": 0}
        got = [pick_account(pp, mine_addr, once), pick_account(pp, mine_addr, once)]
        case("the tile is clicked once a run, by its own address; a second picker is not clicked",
             got == [True, False] and pp.clicked == [f'#tilesHolder [role=button][data-test-id="{mine_addr}"]'])
        real_account, pp = globals()["account"], PickerPage()
        globals()["account"] = lambda: mine_addr
        try:
            clock[0] = 0.0
            got = wait_ready(pp, sso_ready(site), 600, now=tick, sleep=sleep, window=False)
        finally:
            globals()["account"] = real_account
        case("anything after the click (here the picker again) ends the run with NEEDS SIGN-IN",
             got.startswith(NEEDS_SIGN_IN) and len(pp.clicked) == 1)
        clock[0] = 0.0
        case("serve's stop ends the wait for sign-in at once, even with a window",
             wait_ready(None, lambda _: "wait", 600, now=tick, sleep=sleep, window=True, stopped=lambda: True)
             == "stopped" and clock[0] == 0)

        # No window unless the run asked for one: a fake Playwright records what each launch asked for.
        class FakePlaywright:
            def __init__(self):
                self.chromium, self.calls = self, []

            def launch_persistent_context(self, profile, **kw):
                self.calls.append(kw)
                return "ctx"
        fake, env_was = FakePlaywright(), os.environ.pop(HEADED_ENV, None)
        real_options = globals()["launch_options"]
        try:
            try:
                _launch(fake, f)
            except NotReady:
                pass
            case("a launch is headless by default", fake.calls and fake.calls[-1]["headless"] is True)
            case("... and says so to a caller's sign-in loop", headed() is False)
            _launch(fake, f, window=True)
            case("the one launch a person signs in through (--headed) may show a window",
                 fake.calls[-1]["headless"] is False and headed() is True)
            case("every launch denies a site's permission prompts instead of showing them",
                 all("--deny-permission-prompts" in c["args"] for c in fake.calls))
            globals()["launch_options"] = lambda *a, **k: dict(real_options(*a, **k), headless=False)
            n, refused = len(fake.calls), ""
            try:
                _launch(fake, f)
            except NotReady as e:
                refused = str(e)
            case("a planted visible launch is refused before any browser starts",
                 refused.startswith("REFUSED") and len(fake.calls) == n)
            case("... and so is one that passes --headless=false itself",
                 launch_refusal({"headless": True, "args": ["--headless=false"]}, False) is not None)
            os.environ[HEADED_ENV] = "1"
            case(f"{HEADED_ENV}=1 asks for the window", asked_for_window() is True)
            del os.environ[HEADED_ENV]
            case("... and with nothing set, nothing does", asked_for_window() is False)
        finally:
            globals()["launch_options"], globals()["_HEADED"] = real_options, False
            if env_was is not None:
                os.environ[HEADED_ENV] = env_was

        # Each port has its own record: two serves never share one, and stop on one leaves the rest.
        import socket, subprocess
        sd = os.path.join(td, "state")
        os.makedirs(sd)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        me = {"pid": os.getpid(), "port": 9340, "folder": "", "deadline": 0}
        case("two ports have two records", state_path(9340, sd) != state_path(9341, sd))
        case("a free port is claimed", claim(9340, me, sd) is None)
        case("a second serve on the same port is refused while the first is up",
             claim(9340, dict(me, pid=dead.pid), sd) is not None)
        case("another port is free while that one is held", claim(9341, dict(me, port=9341, pid=dead.pid), sd,
                                                               alive=lambda pid: pid == os.getpid()) is None)
        case("each port's record names its own port",
             record_for(9340, sd)[1]["port"] == 9340 and record_for(9341, sd)[1]["port"] == 9341)
        stop_serve(9341, wait=1, root=sd, alive=lambda pid: False)
        case("stop on one port removes that record only",
             record_for(9341, sd) == (None, None) and record_for(9340, sd)[1] is not None)
        case("stop with no port refuses and leaves every record",
             stop_serve(None, root=sd) == 1 and record_for(9340, sd)[1] is not None)
        case("a refusal names the first free port, past the held one",
             free_port(9340, 5, sd, in_use=lambda p: False) == 9341)
        _write_state(state_path(9342, sd), {"pid": dead.pid, "port": 9342})
        case("a dead serve's record is taken over", claim(9342, dict(me, port=9342), sd) is None)
        if os.name != "nt":          # a zombie and ps are POSIX's; Windows has neither
            zombie = subprocess.Popen([sys.executable, "-c", "pass"])
            for _ in range(100):
                if subprocess.run(["ps", "-o", "stat=", "-p", str(zombie.pid)], capture_output=True,
                                  text=True).stdout.strip().startswith("Z"):
                    break
                time.sleep(0.05)
            case("a serve that exited but is not yet reaped (a zombie) counts as gone, so stop doesn't wait on it",
                 _alive(zombie.pid) is False)
            zombie.wait()
        case("a record with no pid holds nothing", _alive(0) is False and _alive("unknown") is False)
        # Windows, played on any machine: _WIN on, and stand-ins for pw_temp's OpenProcess check, os.kill
        # and taskkill. Not measured on Windows itself.
        import pw_temp, types
        kills, trees = [], []
        saved = (globals()["_WIN"], pw_temp.alive_on_windows, os.kill)
        try:
            globals()["_WIN"], os.kill = True, lambda *a: kills.append(a)
            pw_temp.alive_on_windows = lambda pid: pid == 4242
            win_alive = (_alive(4242), _alive(77), _alive(0))
            win_env = launch_options(os.path.join(td, "w"), chan="msedge")["env"]
            wf = os.path.join(td, "win-serve")
            os.makedirs(wf)
            _write_state(state_path(9350, sd), {"pid": 4242, "port": 9350, "folder": wf})
            asked = []

            def closes_itself(pid):          # up until the stop file lands, as _watch_stop_file makes it
                up = not os.path.exists(os.path.join(wf, STOP_FILE))
                asked.append(up)
                return up
            win_stop = stop_serve(9350, wait=3, root=sd, alive=closes_itself, kill_tree=trees.append)
            trees_then = list(trees)
            stuck = {"up": True}
            _write_state(state_path(9351, sd), {"pid": 4243, "port": 9351, "folder": ""})
            win_kill = stop_serve(9351, wait=1, root=sd, alive=lambda pid: stuck["up"],
                                  kill_tree=lambda pid: (trees.append(pid), stuck.update(up=False)))
        finally:
            globals()["_WIN"], pw_temp.alive_on_windows, os.kill = saved
        case("windows: _alive asks pw_temp's OpenProcess check, never os.kill(pid, 0), which sends CTRL_C_EVENT there",
             win_alive == (True, False, False) and kills == [])
        case("windows: the browser's temp files go in the run's folder through TMP and TEMP too",
             win_env.get("TMP") == win_env.get("TEMP") == win_env.get("MAC_CHROMIUM_TMPDIR") == os.path.join(td, "w", "t"))
        if os.name != "nt":
            mac_env = launch_options(os.path.join(td, "w"), chan="msedge")["env"]
            case("... and here TMP and TEMP are left as they are",
                 (mac_env.get("TMP"), mac_env.get("TEMP")) == (os.environ.get("TMP"), os.environ.get("TEMP")))
        case("windows: stop writes the stop file, the serve closes itself, and nothing is killed",
             win_stop == 0 and asked[0] is True and asked[-1] is False and trees_then == [] and kills == []
             and not os.path.exists(wf)
             and record_for(9350, sd) == (None, None))
        case("windows: a serve that doesn't close (or has no folder) is ended with its tree, taskkill /T",
             win_kill == 0 and trees == [4243] and record_for(9351, sd) == (None, None))
        case("windows has no SIGHUP: a serve stops on SIGTERM, SIGINT and SIGBREAK there",
             _stop_signals(types.SimpleNamespace(SIGTERM=15, SIGINT=2, SIGBREAK=21)) == [15, 2, 21])
        if os.name != "nt":
            case("... and here on SIGTERM, SIGINT and SIGHUP, as before",
                 _stop_signals() == [signal.SIGTERM, signal.SIGINT, signal.SIGHUP])
        wf2 = os.path.join(td, "watch")
        os.makedirs(wf2)
        flag = {"now": False}
        watcher = _watch_stop_file(wf2, flag, interval=0.02)
        time.sleep(0.1)
        before = flag["now"]
        open(os.path.join(wf2, STOP_FILE), "w").close()
        watcher.join(2)
        case("windows: the serve's watcher sets stop once the stop file lands, and not before",
             before is False and flag["now"] is True and not watcher.is_alive())
        # The race: the other serve's record lands between this run's check and its create.
        _write_state(state_path(9345, sd), {"pid": os.getpid(), "port": 9345})
        seen = []
        late = lambda pid: bool(seen.append(pid)) or len(seen) > 1   # dead at the first look, up after
        case("a serve that took the port between the check and the create keeps it",
             claim(9345, dict(me, port=9345, pid=dead.pid), sd, alive=late) is not None
             and record_for(9345, sd)[1]["pid"] == os.getpid())
        _write_state(os.path.join(sd, LEGACY_STATE), {"pid": os.getpid(), "port": 9343})
        case("a serve started before the split holds its own port", claim(9343, dict(me, port=9343), sd) is not None)
        case("... and no other", claim(9344, dict(me, port=9344), sd) is None)
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        busy = srv.getsockname()[1]
        case("a port something else listens on is seen as taken", port_in_use(busy))
        srv.close()
        case("... and free once it closes", not port_in_use(busy))
    finally:
        shutil.rmtree(td, ignore_errors=True)
    print(f"{sum(results)} of {len(results)} planted cases behave as expected.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if args[0] in ("selftest", "--selftest"):
        sys.exit(__import__("kit_config").run_isolated(selftest))
    opts = {"--minutes": SERVE_DEFAULT, "--port": None, "--channel": None}
    rest = list(args[1:])
    headed_flag = "--headed" in rest
    rest = [a for a in rest if a != "--headed"]
    for flag in opts:
        if flag in rest:
            i = rest.index(flag)
            opts[flag] = rest[i + 1] if flag == "--channel" else int(rest[i + 1])
            del rest[i:i + 2]
    if args[0] == "stop":
        sys.exit(stop_serve(opts["--port"]))
    if args[0] == "status":
        sys.exit(status(opts["--port"]))
    if args[0] == "serve" and rest:
        sys.exit(serve(rest[0], opts["--minutes"], opts["--port"] or SERVE_PORT, chan=opts["--channel"],
                       headed=headed_flag))
    print(__doc__)
    sys.exit(2)
