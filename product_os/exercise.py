"""product-os design exercise URL: drive a build into each state its design draws, and
see whether it responds.

The states come from design.plan_states. Each frame is opened at URL with the browser window
as wide as the frame, and each state starts from a fresh load:

    hover   the mouse moves onto the node
    focus   Tab is pressed until focus is on or inside the node; a mouse click doesn't count
    press   the mouse moves onto the node, then holds its button down
    click   the mouse moves onto the node, then clicks
    key     focus goes to the node by Tab where it can, then the keys are pressed
    wait    nothing happens for --wait seconds

For an input, the look before and after is compared: the node's pixels, with 8 px around it so
a focus ring outside its box counts, and its computed style. A press or a click is compared with
the hovered look, so a hover style alone doesn't pass for them. A click or a key also counts a
change anywhere on the page, or in its URL. Each look is taken once the page's transitions have
finished, with every animation that loops forever held at its start, so a pulse or a twinkle
elsewhere on the page isn't taken for a response. A state passes ("responds") when its look
changed. A link in the design passes when the node is, or is inside or holds, a link to the same
URL; it isn't clicked. A click or a key that opens another site, on a scheme or host other than
URL's, responds, and the site isn't loaded.

A timed state is the design drawing motion, which a build usually draws with an animation. It
passes when the node or something inside it runs an animation, or when the node's own look
changes during the wait. A timed state on the frame itself is judged on the page, with
animations held, so only a change such as a new URL or an overlay counts.

Responding is a floor, not a match: it shows the build has the state, not that it looks like the
design's. A node is found by a CSS selector given for it or its component set, else by its
data-figma-node attribute, else by its text (BY_TEXT); the frame itself is the page when nothing
else matches it. A node with no text and no selector isn't found. This needs Playwright and
Chromium: pip install playwright, then playwright install chromium.
"""
import json
import threading
from contextlib import contextmanager
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import design

STYLE = ["color", "background-color", "background-image", "border-top-color",
         "border-bottom-color", "border-left-color", "border-right-color", "border-top-width",
         "outline-style", "outline-width", "outline-color", "box-shadow", "text-decoration-line",
         "opacity", "transform", "filter", "visibility", "animation-name"]
# Every animation, the ones inside a component's open shadow root too, which the document's own
# list leaves out, and the element in the document that shows one inside a shadow root.
ANIMATIONS = """
const animations = () => {
  const all = [...document.getAnimations()];
  const walk = root => { for (const el of root.querySelectorAll("*")) if (el.shadowRoot) {
    all.push(...el.shadowRoot.getAnimations()); walk(el.shadowRoot); } };
  walk(document);
  return all.filter(a => a.effect && a.effect.target);
};
const hostOf = el => { for (let r = el.getRootNode(); r instanceof ShadowRoot; r = el.getRootNode()) el = r.host;
  return el; };
"""
# Read the style with every animation that loops forever taken off, as the screenshots are, so
# a twinkle or a pulse doesn't read as a change. They play again straight after.
READ_STYLE = """(el, props) => {""" + ANIMATIONS + """
  const looping = animations().filter(a =>
    a.playState === 'running' && !isFinite(a.effect.getComputedTiming().endTime));
  looping.forEach(a => a.cancel());
  const style = getComputedStyle(el), out = {};
  for (const p of props) out[p] = style.getPropertyValue(p);
  looping.forEach(a => a.play());
  return out;
}"""
# The names of the animations running on the node or inside it.
RUNNING = """el => {""" + ANIMATIONS + """
  return animations().filter(a => a.playState === 'running' && el.contains(hostOf(a.effect.target)))
    .map(a => a.animationName || a.transitionProperty || 'a script animation'); }"""
SAMPLE_MS = 250
HAS_FOCUS = "el => el === document.documentElement || el.contains(document.activeElement)"
LINK = """el => {
  const a = el.closest('a[href]') || el.querySelector('a[href]');
  return a ? a.href : '';
}"""
# Wait until every running transition or animation that has an end has finished, for at most
# limit ms, then for two frames to paint. One that loops forever is left running.
SETTLED = """async limit => {""" + ANIMATIONS + """
  const ending = animations().filter(a =>
    a.playState === 'running' && isFinite(a.effect.getComputedTiming().endTime));
  await Promise.race([Promise.all(ending.map(a => a.finished.catch(() => null))),
                      new Promise(done => setTimeout(done, limit))]);
  await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
  return ending.length;
}"""
SETTLE_LIMIT_MS = 3000
# Where the pointer waits between moves: just off the page, where it hovers nothing. At (0, 0) it
# hovers whatever is in the top left corner, such as a menu a hover opens.
PARK = (-1, -1)
FRAMES = "() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))"
FAILED = {"no change", "not found", "not reached", "no link", "wrong link", "error"}
PAD = 8
MARK = "data-product-os-target"
# Find a node by its text, as a person would: the smallest shown element whose rendered text is
# the node's first text, in any case since CSS can change it, the place-th of those; then the
# nearest link, button or focusable element around it, widened until it holds the node's second
# text too. Rendered text leaves out what is hidden, such as a closed menu's items. The element
# found is marked with MARK, which changes nothing it draws.
BY_TEXT = """([texts, place]) => {
  const plain = s => (s || '').replace(/\\u200b/g, '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const [first, second] = texts.map(plain);
  const shown = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden'; };
  const all = [...document.querySelectorAll('body *')].filter(el => shown(el) && plain(el.innerText) === first);
  const smallest = all.filter(el => !all.some(other => other !== el && el.contains(other)));
  const el = smallest[place];
  if (!el) return false;
  const control = 'a[href], button, summary, [tabindex], [role=button], [role=tab], [role=link]';
  let target = el.closest(control) || el;
  if (second) {
    let up = target;
    while (up && !plain(up.innerText).includes(second)) up = up.parentElement;
    if (up) target = up.closest(control) || up;
  }
  target.setAttribute('MARK', '');
  return true;
}""".replace("MARK", MARK)


class ExerciseError(Exception):
    """The browser can't run the states. The message says why."""


def _origin(url):
    parts = urlsplit(url or "")
    return parts.scheme.lower(), parts.netloc.lower()


def stay_on(page, url):
    """Stop the page from loading another site in its own window, and return the list each
    stopped address is added to. A click is followed only on the URL's own scheme and host, so
    exercising a build never opens a site the build links to."""
    home, left = _origin(url), []

    def stop(route):
        request = route.request
        if request.is_navigation_request() and request.frame == page.main_frame:
            left.append(request.url)
            route.abort()
        else:
            route.continue_()

    page.route(lambda address: _origin(address) != home, stop)
    return left


def same_url(a, b):
    def norm(url):
        parts = urlsplit(url or "")
        return (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/",
                parts.query, parts.fragment)
    return norm(a) == norm(b)


def selector_for(state, selectors):
    """(CSS selector, which visible match) for the state's node. A selector given for the node
    takes its first visible match. One given for its component set, by id or by name, takes
    the match with the instance's place among that set's instances in the frame."""
    if state.node in selectors:
        return selectors[state.node], 0
    for key in (state.component_set, state.set_name):
        if key and key in selectors:
            return selectors[key], state.ordinal
    return f'[data-figma-node="{state.node}"]', 0


def _find(page, state, selectors):
    """The node's element: by selector, else data-figma-node, else its text, else the page for
    the frame itself."""
    selector, nth = selector_for(state, selectors)
    found = page.locator(selector)
    shown = [found.nth(i) for i in range(found.count()) if found.nth(i).is_visible()]
    if nth < len(shown):
        return shown[nth]
    if (state.texts and selector.startswith("[data-figma-node=")
            and page.evaluate(BY_TEXT, [state.texts, state.text_ordinal])):
        return page.locator(f"[{MARK}]")
    if state.node == state.frame:
        return page.locator("html")
    return None


def _look(page, element, whole_page, settle=True, pad=PAD):
    """What the state is judged on: the node's pixels, with pad px around them, and its style,
    and the page's when asked. Looping animations are held at their start and a transition
    under way is shown finished, so a look half way through one isn't compared. With settle,
    the look also waits for transitions to finish, so styles read are their end values."""
    look = {"pixels": None, "style": None, "page": None, "url": page.url}
    if settle:
        try:
            page.evaluate(SETTLED, SETTLE_LIMIT_MS)
        except Exception:  # the page went away mid-wait; what's left is judged below
            pass
    try:
        element.scroll_into_view_if_needed(timeout=2000)
        box = element.bounding_box(timeout=2000)
        look["style"] = element.evaluate(READ_STYLE, STYLE)
        if box and not pad:
            # Playwright measures the node after holding animations, so a box that is still
            # sliding in is pictured where it ends up, the same in every look.
            look["pixels"], box = element.screenshot(animations="disabled", timeout=5000), None
    except Exception:  # the click took the node away, or the page with it
        box = None
    if box:
        size = page.viewport_size
        x, y = max(box["x"] - pad, 0), max(box["y"] - pad, 0)
        width = min(box["x"] + box["width"] + pad, size["width"]) - x
        height = min(box["y"] + box["height"] + pad, size["height"]) - y
        if width > 0 and height > 0:
            look["pixels"] = page.screenshot(clip={"x": x, "y": y, "width": width,
                                                   "height": height}, animations="disabled")
    if whole_page:
        look["page"] = page.screenshot(animations="disabled")
    return look


def _moves(page, element, wait_s):
    """(status, detail, shots) for a timed state on a node: it responds when the node or
    something inside it runs an animation, or when its look changes during the wait. The first
    look comes as soon as the node is in view, two frames on, so a script that reveals it on
    scrolling has run and a one-off change at the design's timeout is still ahead. Only the
    node's own box counts, so a neighbour's motion doesn't."""
    element.scroll_into_view_if_needed(timeout=2000)
    page.evaluate(FRAMES)
    running = sorted(set(element.evaluate(RUNNING)))
    before = _look(page, element, False, settle=False, pad=0)
    if running:
        return "responds", "it animates: " + ", ".join(running), (before["pixels"], None)
    for _ in range(max(1, int(wait_s * 1000 / SAMPLE_MS))):
        page.wait_for_timeout(SAMPLE_MS)
        after = _look(page, element, False, settle=False, pad=0)
        changes = _changes(before, after)
        if changes:
            return "responds", "; ".join(changes), (before["pixels"], after["pixels"])
    return "no change", f"nothing on it moved in {wait_s:g} s", (before["pixels"], after["pixels"])


def _changes(before, after):
    out = []
    if before["pixels"] != after["pixels"]:
        out.append("its pixels changed")
    if before["style"] and after["style"]:
        styles = [p for p in STYLE if before["style"][p] != after["style"][p]]
        if styles:
            out.append("its style changed: " + ", ".join(styles))
    if before["page"] is not None and before["page"] != after["page"]:
        out.append("the page changed")
    if before["url"] != after["url"]:
        out.append(f"the URL became {after['url']}")
    return out


def _tab_to(page, element, presses):
    for _ in range(presses):
        page.keyboard.press("Tab")
        if element.evaluate(HAS_FOCUS):
            return True
    return False


def exercise_one(page, url, state, selectors, settle_ms, wait_s, max_tabs):
    """(status, detail, (before, after) screenshots or None) for one state that has an input."""
    left = stay_on(page, url)
    page.goto(url, wait_until="load")
    page.mouse.move(*PARK)
    page.wait_for_timeout(settle_ms)
    element = _find(page, state, selectors)
    if element is None:
        selector, nth = selector_for(state, selectors)
        return "not found", f"no visible match {nth + 1} for {selector}", None
    if state.expect.get("kind") == "url":
        want = state.expect.get("target") or ""
        href = element.evaluate(LINK)
        if not href:
            return "no link", f"it isn't a link; the design links to {want}", None
        if not same_url(href, want):
            return "wrong link", f"it links to {href}; the design links to {want}", None
        return "responds", f"it links to {href}", None
    if state.do == "wait" and state.node != state.frame:
        return _moves(page, element, wait_s)
    # Bring the node into view first and let the page settle, so a section that reveals itself
    # on scrolling has finished before the first look.
    element.scroll_into_view_if_needed(timeout=2000)
    page.wait_for_timeout(settle_ms)
    page.evaluate(SETTLED, SETTLE_LIMIT_MS)
    whole_page = state.do in ("click", "key", "wait")
    if state.do in ("press", "click"):
        element.hover()
        page.wait_for_timeout(settle_ms)
    if state.do == "key" and state.node != state.frame:
        _tab_to(page, element, max_tabs)
    before = _look(page, element, whole_page)
    if state.do == "hover":
        element.hover()
    elif state.do == "focus":
        if not _tab_to(page, element, max_tabs):
            return "not reached", f"{max_tabs} presses of Tab never reached it", None
    elif state.do == "press":
        page.mouse.down()
    elif state.do == "click":
        element.click()
        page.wait_for_load_state("load")
    elif state.do == "key":
        page.keyboard.press(state.keys)
    elif state.do == "wait":
        page.wait_for_timeout(int(wait_s * 1000))
    page.wait_for_timeout(settle_ms)
    if left:  # it tried to open another site, which stay_on stopped
        return "responds", f"it opens {left[0]}, which isn't followed", (
            before["pixels"] or before["page"], None)
    if state.do == "click" and not same_url(page.url, before["url"]):
        # it went somewhere: no need to look again
        return "responds", f"the URL became {page.url}", (before["pixels"] or before["page"], None)
    after = _look(page, element, whole_page)
    if state.do == "press":
        page.mouse.up()
    changes = _changes(before, after)
    shots = (before["pixels"] or before["page"], after["pixels"] or after["page"])
    if not changes:
        return "no change", f"after {state.do}, the same pixels and the same style", shots
    return "responds", "; ".join(changes), shots


@contextmanager
def chromium():
    """A headless Chromium from Playwright. Raises ExerciseError when there is none."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ExerciseError("design exercise needs Playwright: pip install playwright, then "
                            "playwright install chromium") from None
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as err:
            raise ExerciseError(f"Chromium didn't start: {str(err).splitlines()[0]}. Run "
                                "playwright install chromium") from None
        try:
            yield browser
        finally:
            browser.close()


@contextmanager
def serving(folder):
    """The base URL of a server on 127.0.0.1 for a built site's folder, such as dist/."""
    if not Path(folder).is_dir():
        raise ExerciseError(f"{folder}: not a folder to serve")
    handler = partial(_QuietFiles, directory=str(folder))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


class _QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def exercise(folder, url, frames=None, selectors=None, evidence=None, settle_ms=300, wait_s=5.0,
             max_tabs=200, height=900, browser=None, serve=None, accepted=None):
    """A result for every planned state: the state's fields plus status and detail. With serve,
    a built site's folder, url is a path on it, such as /. Opens a Chromium unless given one,
    and only when an input reaches a state. A state that fails and has an entry in accepted,
    from read_accepted, is "accepted", with the entry's reason. Raises design.BaselineError for
    an unusable baseline and ExerciseError when the browser can't run."""
    states = design.plan_states(folder, frames)
    if serve:
        with serving(serve) as base:
            return exercise(folder, base + "/" + url.lstrip("/"), frames, selectors, evidence,
                            settle_ms, wait_s, max_tabs, height, browser, None, accepted)
    if browser is None and any(s.do != "none" for s in states):
        with chromium() as browser:
            return exercise(folder, url, frames, selectors, evidence, settle_ms, wait_s,
                            max_tabs, height, browser, None, accepted)
    selectors, accepted = selectors or {}, accepted or {}
    results = []
    for number, state in enumerate(states, 1):
        status, detail, shots = "not exercised", state.why_not, None
        if state.do != "none":
            page = browser.new_page(viewport={"width": int(state.width or 1280), "height": height})
            try:
                status, detail, shots = exercise_one(page, url, state, selectors, settle_ms,
                                                     wait_s, max_tabs)
            except Exception as err:
                status, detail, shots = "error", str(err).splitlines()[0], None
            finally:
                page.close()
        why = accepted.get((state.node, state.state))
        if why is not None and status in FAILED:
            status, detail = "accepted", f"{status}, accepted: {why}"
        result = {**asdict(state), "status": status, "detail": detail, "evidence": []}
        if evidence and shots:
            stem = f"{number:03d}-{design.folder_name(state.node)}-{state.do}"
            for side, data in zip(("before", "after"), shots):
                if data:
                    path = Path(evidence) / design.folder_name(state.frame) / f"{stem}-{side}.png"
                    design.write_atomic(path, data)
                    result["evidence"].append(path.as_posix())
        results.append(result)
    if evidence:
        design.write_json(Path(evidence) / "results.json", {"url": url, "results": results})
    return results


def read_selectors(path):
    """{node id: CSS selector} from a JSON file."""
    try:
        selectors = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ExerciseError(f"{path} could not be read") from None
    if not isinstance(selectors, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in selectors.items()):
        raise ExerciseError(f"{path} must be a JSON object from Figma node id to CSS selector")
    return selectors


def read_accepted(path):
    """{(node id, state): reason} from a JSON list of {"node", "state", "why"}: the drawn states
    a project built differently on purpose. Each why says what was decided, and where."""
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ExerciseError(f"{path} could not be read") from None
    if not isinstance(entries, list) or not all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) and e.get(k).strip()
                                        for k in ("node", "state", "why")) for e in entries):
        raise ExerciseError(f"{path} must be a JSON list of objects, each with a node, the "
                            "state as design states lists it, and why")
    return {(e["node"], e["state"]): e["why"] for e in entries}
