"""product-os gates URL: objective checks on a built page, at each width its design draws.

    keyboard   every element a mouse can click can be reached with Tab, and Tab can leave
               every element it reaches
    focus      every element Tab reaches looks different while it has focus
    overflow   no element starts on the screen and runs past its right edge, and the page
               doesn't scroll sideways
    images     every image loads, and has enough pixels for the size it's drawn at, at 2x
    motion     with reduced motion asked for, nothing animates forever or for more than 5 s

None of these needs the design to draw anything. A focus ring, a tap target or a sharp
image is rarely drawn, and a build that lacks one is still wrong. Each gate passes or fails
on something measured, and a failure names the element by a short CSS path, with the number.

The widths are the frames' widths in the baseline, or --width, or 1280 and 390 with neither.
Every page starts from a fresh load and stays on the URL's site (exercise.stay_on). This needs
Playwright and Chromium: pip install playwright, then playwright install chromium.
"""
import base64
import json
import math
from contextlib import contextmanager
from pathlib import Path

from . import design, exercise

JS = Path(__file__).with_name("gates_js")


def _js(name):
    """The in-page script in gates_js/<name>.js. Each is a piece of a function the constants
    below put together, so it isn't valid alone; tests/test_gates.py parses every whole one."""
    return (JS / f"{name}.js").read_text(encoding="utf-8")


GATES = ("keyboard", "focus", "overflow", "images", "motion")
WIDTHS = (1280, 390)  # with no baseline and no --width: a laptop and a phone
HEIGHT = 900
SCALE = 2  # the screen density the images gate asks for
BLUR = 1.1  # an image drawn more than 10% larger than its pixels allow is blurry
MOTION_LIMIT_MS = 5000  # WCAG 2.2.2: motion that runs longer than 5 s needs a way to stop it
MAX_TABS = 400
MAX_FOCUS = 80  # Tab stops whose focus look is compared, per width
MAX_TRIES = 20  # closed boxes hovered, and button-like elements pressed, per width
SHOWN_LIMIT = 10  # findings printed per gate

HELPERS = _js("helpers") + exercise.ANIMATIONS

CLICKABLE = "() => {" + HELPERS + _js("clickable")

# Each Tab stop, the element that shows its focus, and for a native radio button its group: Tab
# reaches only one radio in a group, and the arrow keys move between them.
TARGETS = "() => {" + HELPERS + _js("targets")

# Controls that would be in the Tab order if they were shown: the links in a closed menu, say.
# A walk with Tab has to open them somehow, or a hover is the only way in.
HIDDEN = "() => {" + HELPERS + _js("hidden")

SHOWN_NOW = "paths => {" + HELPERS + _js("shown_now")
SHOWN = "path => {" + HELPERS + _js("shown")
# The paths among paths of elements inside the box at box.
INSIDE = "([box, paths]) => {" + HELPERS + _js("inside")

# The Tab stops a keyboard user presses Enter or Space on: a native button, which can still act
# on a pointer event that no key sends, and an element that acts on a click but isn't a native
# control, such as a div with role=button and tabindex=0.
BUTTONLIKE = "paths => {" + HELPERS + _js("buttonlike")
# Those of the paths that a double-click works, and a single click may not.
DOUBLE = "paths => {" + HELPERS + _js("double")

# Tab stops a drag works: a handle with a resize, grab or move cursor, or a slider by its role.
# A keyboard user moves one with the arrow keys.
DRAGGABLE = "paths => {" + HELPERS + _js("draggable")
DISABLED = "() => {" + HELPERS + _js("disabled")
STILL_DISABLED = "paths => {" + HELPERS + _js("still_disabled")

# Whether an action did something: the elements the page changed after it, less those that
# change by themselves, as a clock does. A scroll isn't a change, since Space scrolls a long page
# whatever has focus.
NOTE_CHANGES = "() => {" + HELPERS + _js("changes_start")
NOTED = "() => {" + HELPERS + _js("changes")
RESTLESS_MS = 1000  # how long a fresh load is watched for what changes by itself


def _restless(page, url, ms=RESTLESS_MS):
    """The elements that change by themselves on a fresh load, within ms of it settling."""
    _fresh(page, url)
    try:
        page.evaluate(NOTE_CHANGES)
        page.wait_for_timeout(ms)
        return frozenset(page.evaluate(NOTED))
    except Exception:
        return frozenset()


def _changed(page, noise):
    """The elements the page changed since NOTE_CHANGES or the last call, less noise."""
    return set(page.evaluate(NOTED)) - noise

# A native control taken out of the Tab order. Inside a widget that moves focus with the arrow
# keys (a tab list, a menu, a toolbar), the items other than the current one rightly have -1.
# One that a box hiding its overflow hides, as a carousel hides the slides not showing, isn't
# usable with a mouse either.
SKIPPED = "() => {" + HELPERS + _js("skipped")
# Where the links among the elements at paths go. A link only a mouse reaches is no loss when a
# link Tab reaches goes to the same place, as a card's picture often repeats its title link.
HREFS = "paths => {" + HELPERS + _js("hrefs")
# The paths among paths inside aria-hidden="true", which hides them from a screen reader.
ARIA_HIDDEN = "paths => {" + HELPERS + _js("aria_hidden")

# Whether the element that has focus can be seen on the screen.
ON_SCREEN = "() => {" + HELPERS + _js("on_screen")
SCROLL_STILL = "async ([limit, path]) => {" + HELPERS + _js("scroll_still")
# Scrolls an element to the middle of the window at once, even in a box that scrolls smoothly,
# so a picture isn't taken partway through a scroll it started.
TO_MIDDLE = "el => el.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'})"
SCROLL_LIMIT_MS = 1500  # a smooth scroll to a card in a row takes about 1 s

# What is on top of the element at path all over, as a sticky bar can be over a field scrolled
# under it: the element on top at five points across each line of it, none of them the element,
# inside it or around it. None when any of it shows, or it's past the screen's edge. Whether what
# is on top paints anything there is for _paints_over.
COVERED = "path => {" + HELPERS + _js("covered")
SEE_THROUGH = "([path, through]) => {" + HELPERS + _js("see_through")
# The boxes around an element with their style, for a style that focus inside one changes.
ANCESTRY = "([path, props]) => {" + HELPERS + _js("ancestry")

ACTIVE = "() => {" + HELPERS + _js("active")
WITHIN = "() => {" + HELPERS + _js("within")
# Tab presses that may stay on one element while focus moves on inside it: a frame from another
# site, whose links can't be counted from outside, and a date and time field's parts.
INSIDE_LIMIT = {"frame": 50, "field": 8}
NAMED_KEY = "() => {" + HELPERS + _js("named_key")
REFOCUS_MS = 300  # long enough for a script that takes focus back after a moment, as on blur
IFRAMES = "paths => {" + HELPERS + "return paths.filter(p => { const el = find(p); return el && el.localName === 'iframe'; }); }"
# Lets go of a field that took focus as the page loaded, as a click elsewhere would.
LET_GO = "() => { const el = document.activeElement; if (el && el !== document.body) el.blur(); }"

OVERFLOW = "() => {" + HELPERS + _js("overflow")

IMAGES = "async scale => {" + HELPERS + _js("images").replace("BLUR", str(BLUR))

SCROLL_THROUGH = _js("scroll_through")

MOVING = "limit => {" + HELPERS + _js("moving")


# Motion a script drives, such as a requestAnimationFrame loop or a carousel on a timer, sets
# an element's style or class over and over. Watched for this long, past the 5 s mark.
WATCH_MS = 6000  # long enough to see a carousel that moves every 5 s change twice
CHANGES = 2  # changes in that time that count as moving

# An SVG's own <animate> runs outside CSS, so reduced motion has to stop it some other way.
SMIL = "limit => {" + HELPERS + _js("smil")
WATCH = _js("watch")
# What changed while it was watched: elements a script restyled CHANGES times or more, and the
# element under each box of pixels that kept changing with no animation, style or class change
# to explain it: a <marquee>, a GIF, a video, a canvas or a closed shadow root. Text a script
# rewrites, such as a clock, isn't motion.
CHANGED = "([boxes, named]) => {" + HELPERS + _js("changed").replace("CHANGES", str(CHANGES))
FRAME_MS = 1000  # one picture a second while it's watched
CELL = 16  # px; pixels are grouped in squares this size to find what moved


class GateError(Exception):
    """Gates that can't run. The message says why."""


def widths_from(baseline=None, widths=None):
    """The widths to check: those given, else the baseline frames', else WIDTHS."""
    if widths:
        return sorted({int(w) for w in widths}, reverse=True)
    if baseline and Path(baseline, "index.json").is_file():
        found = {int(f["width"]) for f in design.read_index(baseline)["frames"].values()
                 if isinstance(f, dict) and isinstance(f.get("width"), (int, float)) and f["width"] > 0}
        if found:
            return sorted(found, reverse=True)
    return list(WIDTHS)


def _open(browser, url, width, **options):
    page = browser.new_page(viewport={"width": width, "height": HEIGHT}, **options)
    page.add_init_script(LISTENERS_SEEN)
    exercise.stay_on(page, url)
    page.goto(url, wait_until="load")
    page.mouse.move(*exercise.PARK)
    page.evaluate(exercise.SETTLED, exercise.SETTLE_LIMIT_MS)
    return page


def _n(items, word):
    n = items if isinstance(items, int) else len(items)
    return f"{n} {word}" + ("" if n == 1 else "s")


def _result(width, gate, findings, passed, failed):
    status = "fail" if findings else "pass"
    return {"width": width, "gate": gate, "status": status,
            "detail": failed(findings) if findings else passed, "findings": findings}


# How Playwright says a navigation it didn't start landed while it loaded or read the page.
STRAY = ("interrupted by another navigation", "Execution context was destroyed")


def _fresh(page, url, again=True):
    """Load url again as a first visit, as _open did: no cookie or stored data a probe before
    left, such as the consent that hides a cookie banner. A link the probe before followed can
    land partway through, so then it starts over once, after that page has loaded."""
    page.context.clear_cookies()
    try:
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    except Exception:
        pass  # a page mid-navigation, or one that blocks storage, has none to clear
    try:
        page.goto(url, wait_until="load")
        page.mouse.move(*exercise.PARK)
        page.evaluate(exercise.SETTLED, exercise.SETTLE_LIMIT_MS)
    except Exception as err:
        if not again or not any(sign in str(err) for sign in STRAY):
            raise
        page.wait_for_load_state("load")
        _fresh(page, url, again=False)


A_FRAME = _js("a_frame")
# Each box around the element at path, and the page, with where it's scrolled to, so a picture
# that scrolls the element to the middle can put them back: the walk measures where Tab left them.
KEEP_SCROLL = "path => {" + HELPERS + _js("keep_scroll")
SCROLLS = "path => {" + HELPERS + _js("scrolls")
SCROLL_AS = "scrolls => {" + HELPERS + _js("scroll_as")
PUT_SCROLL_BACK = _js("put_scroll_back")
HOLD = "() => {" + HELPERS + _js("hold")
RELEASE = "() => {" + HELPERS + _js("release")


def _locate(page, path):
    """The element at a path from pathOf. Playwright's CSS goes into open shadow roots on its own,
    so the part after a host is looked for inside it."""
    return page.locator(path.replace(" >>> ", " >> ")).first


def _ratio(contrast):
    """A contrast as a finding prints it, rounded down to a tenth, so one just short of 3:1 never
    reads 3.0:1."""
    return f"{math.floor(contrast * 10 + 1e-9) / 10:.1f}"  # 2.3 * 10 is 22.999...


def _pixel(at):
    """The pixel edge nearest at, a half rounded up, as the browser puts a box's edge."""
    return math.floor(at + 0.5)


def _look_at(page, path, pad=exercise.PAD):
    """The element at path: its pixels with pad px around them, its style, and the boxes around
    it with theirs, and where it was pictured, for _look_over. Animations are held as the
    screenshot holds them while it's measured and pictured, so what is measured is what is
    pictured: one that ends, such as a hero rising in, at its end, and one that loops taken off."""
    target = _locate(page, path)
    look = {"pixels": None, "style": None, "page": None, "url": page.url, "around": []}
    page.evaluate(HOLD)
    page.evaluate(KEEP_SCROLL, path)
    try:
        target.evaluate(TO_MIDDLE)
        page.evaluate(SCROLL_STILL, [SCROLL_LIMIT_MS, path])
        look["style"] = target.evaluate(exercise.READ_STYLE, exercise.STYLE)
        look["around"] = page.evaluate(ANCESTRY, [path, exercise.STYLE])
        box, size = target.bounding_box(timeout=2000), page.viewport_size
        if box:
            x, y = max(box["x"] - pad, 0), max(box["y"] - pad, 0)
            # Each edge where the browser paints it, on the nearest pixel, as the screenshot puts
            # the clip's: a box 75.5 px wide off the grid paints 75 or 76 columns, not one more.
            left, top = _pixel(box["x"]), _pixel(box["y"])
            look["box"] = [left - _pixel(x), top - _pixel(y), _pixel(box["x"] + box["width"]) - left,
                           _pixel(box["y"] + box["height"]) - top]
            look["whole"] = (box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= size["width"]
                             and box["y"] + box["height"] <= size["height"])
            width = min(box["x"] + box["width"] + pad, size["width"]) - x
            height = min(box["y"] + box["height"] + pad, size["height"]) - y
            if width > 0 and height > 0:
                look["clip"] = {"x": x, "y": y, "width": width, "height": height}
                look["scrolls"] = page.evaluate(SCROLLS, path)
                look["pixels"] = page.screenshot(clip=look["clip"], animations="disabled")
    finally:
        page.evaluate(PUT_SCROLL_BACK)
        page.evaluate(RELEASE)
    return look


def _moved(plain, focused):
    """Whether focus changed the size of the stop's box, or brought it into the window from
    outside, as a skip link hidden in a 1 px box or above the page until it has focus is. Then a
    picture around its box without focus isn't of the part of the page focus changed."""
    if not focused.get("clip"):
        return False
    if not plain.get("box"):
        return True
    # A box off the pixel grid can paint a column or a row more in one place than in another.
    grew = any(abs(a - b) > 1 for a, b in zip(plain["box"][2:], focused["box"][2:]))
    return grew or (focused["whole"] and not plain["whole"])


def _look_over(page, look):
    """The part of the page look was pictured over, pictured as the page is now: the window and
    the boxes around the stop scrolled as they were then, and animations held as _look_at holds
    them. As WCAG 2.4.13 compares them, the same pixels with focus and without."""
    over = {"pixels": None, "style": None, "page": None, "url": page.url, "around": []}
    page.evaluate(HOLD)
    try:
        page.evaluate(SCROLL_AS, look["scrolls"])
        over["pixels"] = page.screenshot(clip=look["clip"], animations="disabled")
    finally:
        page.evaluate(PUT_SCROLL_BACK)
        page.evaluate(RELEASE)
    return over


# Two pictures of the same size, decoded, and off(i): whether the pixel at i differs by more than
# a faint edge does. Run in a blank page, so a site's content security policy can't block it.
_PAIR = _js("pair")
# How many pixels differ; the contrast of the part outside the element's box, and of the part
# inside it, against the colours touching each; what most changed pixels reach against their own
# colour before; and on how many sides of the box focus shows.
CONTRAST = "async ([a, b, cut, box]) => { const crop = true;" + _PAIR + _js("contrast")
# Which squares of cell px have at least least pixels that differ, numbered across, then down.
CELLS = "async ([a, b, cut, cell, least]) => { const crop = false;" + _PAIR + _js("cells")
EDGE = 40  # a channel difference above this is a change, not anti-aliasing
SEEN = 3  # pixels that have to change for a change to be seen
# WCAG 1.4.11, at AA: what shows a state, focus included, has 3:1 against the colours beside it.
# 2.4.13, at AAA, asks 3:1 between the pixels with focus and without, over at least a 2 px ring; a
# change that passes AA and not that is listed as weak, with why, and doesn't fail.
RATIO = 3


def _shows(plain, focused, blank):
    """How focus shows, from a look without it and one with it: None when the two are the same
    to the eye, else CONTRAST's numbers, with "ring", the pixels in a ring 2 px thick around the
    element, 2.4.13's least. A number that can't be measured is None. Pixels decide when there are
    both: a ring that's clipped, or drawn in the colour behind it, changes the style but nothing
    anyone sees. blank is a page on about:blank that compares them."""
    unmeasured = {"changed": None, "outside": None, "inside": None, "shift": None, "sides": None, "ring": None}
    if plain["pixels"] and focused["pixels"]:
        if plain["pixels"] == focused["pixels"]:
            return None
        seen = blank.evaluate(CONTRAST, [base64.b64encode(plain["pixels"]).decode(),
                                         base64.b64encode(focused["pixels"]).decode(), EDGE, focused.get("box")])
        if seen is not None:
            if seen["changed"] < SEEN:
                return None
            width, height = (focused.get("box") or [0, 0, 0, 0])[2:]
            return {**seen, "ring": 4 * (width + height)}
    return unmeasured if exercise._changes(plain, focused) else None


def _restyled(plain, focused):
    """The nearest box around the element whose style focus changed, as :focus-within does."""
    before = {a["path"]: a["style"] for a in plain.get("around") or []}
    return next((a["path"] for a in focused.get("around") or []
                 if a["path"] in before and before[a["path"]] != a["style"]), None)


def _paints_over(page, cover, path, blank):
    """Whether the element at cover, on top of the element at path, paints anything there: the
    element's box looks different with cover made see-through. A transparent layer, or the
    stretched ::after of a card's link, is on top and paints nothing. Yes when it can't be told."""
    try:
        box, size = _locate(page, path).bounding_box(timeout=2000), page.viewport_size
        x, y = max(box["x"], 0), max(box["y"], 0)
        clip = {"x": x, "y": y, "width": min(box["x"] + box["width"], size["width"]) - x,
                "height": min(box["y"] + box["height"], size["height"]) - y}
        if clip["width"] <= 0 or clip["height"] <= 0:
            return True
        shown = page.screenshot(clip=clip, animations="disabled")
        page.evaluate(SEE_THROUGH, [cover, True])
        try:
            under = page.screenshot(clip=clip, animations="disabled")
        finally:
            page.evaluate(SEE_THROUGH, [cover, False])
        if shown == under:
            return False
        seen = blank.evaluate(CONTRAST, [base64.b64encode(shown).decode(), base64.b64encode(under).decode(), EDGE])
        return seen is None or seen["changed"] >= SEEN
    except Exception:
        return True


def _acts(page, url, path, key=None, double=False, noise=frozenset()):
    """Whether pressing key on the element at path, or with no key clicking it, or double-clicking
    it, changes the page: its address or an element other than those in noise, or starts a
    navigation or opens something outside the page. A scroll doesn't count, since Space scrolls by
    itself. None when it can't be told: the page threw while it was read and nothing was seen to
    open, as when a navigation the key started replaced the page. A caller reports a key as dead
    only on False."""
    _fresh(page, url)
    target = _locate(page, path)
    with _opened(page) as opened:
        try:
            if key:
                target.focus(timeout=2000)
            else:
                target.hover(timeout=2000)  # what the pointer arriving does isn't the click's doing
            href = page.url
            page.evaluate(NOTE_CHANGES)
            if key:
                page.keyboard.press(key)
            elif double:
                target.dblclick(timeout=2000)
            else:
                target.click(timeout=2000)
            page.wait_for_timeout(300)
            return bool(opened) or page.url != href or bool(_changed(page, noise))
        except Exception:
            return True if opened else None


@contextmanager
def _opened(page):
    """A list that fills while it's open with what the page opens outside itself: a file
    picker, a dialog, a popup or a download, each closed or turned down, or a navigation of the
    page itself, counted even when stay_on or a recording stops it."""
    opened = []
    def navigation(request):
        if request.is_navigation_request() and request.frame == page.main_frame:
            opened.append("a navigation")
    def dialog(d):
        opened.append("a dialog")
        d.dismiss()
    def popup(p):
        opened.append("a popup")
        p.close()
    handlers = {"dialog": dialog, "popup": popup, "filechooser": lambda _: opened.append("a file picker"),
                "download": lambda d: (opened.append("a download"), d.cancel()), "request": navigation}
    for event, handler in handlers.items():
        page.on(event, handler)
    try:
        yield opened
    finally:
        for event, handler in handlers.items():
            page.remove_listener(event, handler)


# Run before the page's own scripts: notes the events each element gets a listener for, since a
# handler added in a script shows no cursor or attribute. A key listener on a form can cancel Enter
# on a link inside it, and a click or wheel listener makes an element something a mouse uses.
LISTENERS_SEEN = _js("listeners_seen")
# Links among the Tab stops with a key listener on them or on a box around them, short of the body.
LINKS_UNDER_KEYS = "paths => {" + HELPERS + _js("links_under_keys")
# Shown elements a mouse can pick: a pointer cursor, an onclick, or an option's role.
PICKABLE = "() => {" + HELPERS + _js("pickable")
TEXT_FIELDS = "paths => {" + HELPERS + _js("text_fields")
LETTERS = "scpmbatdl"  # common first letters, typed one at a time until choices show


def _choices_unreached(page, url, path, letters=LETTERS, noise=frozenset()):
    """Whether typing in the field at path shows choices a mouse can pick, and neither the down
    arrow nor Tab gets to them. Each letter is typed alone, until one shows choices."""
    _fresh(page, url)
    try:
        field = _locate(page, path)
        field.focus(timeout=2000)
        before = set(page.evaluate(PICKABLE))
        for letter in letters:
            field.fill("")
            page.keyboard.type(letter)
            page.wait_for_timeout(300)
            shown = set(page.evaluate(PICKABLE)) - before - {path}
            if not shown:
                continue
            page.evaluate(NOTE_CHANGES)
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(200)
            if _changed(page, noise):
                return False
            page.keyboard.press("Tab")
            page.wait_for_timeout(200)
            return page.evaluate(ACTIVE) not in shown
        return False
    except Exception:
        return False


def _opened_unreached(page, url, path, opened):
    """Whether, after Enter on the element at path opens the Tab stops in opened, Tab, Shift+Tab
    and the down arrow all fail to reach one, each tried from a fresh open."""
    for key in ("Tab", "Shift+Tab", "ArrowDown"):
        _fresh(page, url)
        try:
            _locate(page, path).focus(timeout=2000)
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            if page.evaluate(ACTIVE) in opened:
                return False
            page.keyboard.press(key)
            page.wait_for_timeout(200)
            if page.evaluate(ACTIVE) in opened:
                return False
        except Exception:
            return False
    return True


def _way_out(page, loop):
    """How focus gets out of the Tab stops in loop, which Tab alone goes round, pressed from where
    the walk is, in the ways ACT's rules on keyboard traps allow: Escape, after which what held
    focus is gone ("closed") or Tab lands outside the loop ("Escape"); Shift+Tab, back out of it
    ("Shift+Tab"), since one direction is enough; or the key the page's own text says moves focus
    on. None when nothing does, and "can't tell" when the page couldn't be read. Where focus is
    gets read REFOCUS_MS after each key, by when a script that takes it back has. A frame in the
    loop can take up to INSIDE_LIMIT["frame"] more presses of Shift+Tab to get back out of."""
    def out():
        page.wait_for_timeout(REFOCUS_MS)
        return page.evaluate(ACTIVE) not in loop
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if not page.evaluate(SHOWN_NOW, loop):
            return "closed"
        page.keyboard.press("Tab")
        if out():
            return "Escape"
        for _ in range(len(loop) + 1 + (INSIDE_LIMIT["frame"] if page.evaluate(IFRAMES, loop) else 0)):
            page.keyboard.press("Shift+Tab")
            if out():
                return "Shift+Tab"
        key = page.evaluate(NAMED_KEY)
        if key:
            page.keyboard.press(key)
            page.wait_for_timeout(300)
            page.keyboard.press("Tab")
            if out():
                return key
    except Exception:
        return "can't tell"
    return None


def _walk_back(page, stops, limit):
    """The Tab stops Shift+Tab reaches, going on backwards from where focus is, until it's round
    the page to one it reached before, or round a few of its own: what a keyboard reaches past a
    loop that only Shift+Tab leaves."""
    found, seen, away, left, last = [], set(), 0, False, None
    for _ in range(limit):
        here = page.evaluate(ACTIVE)
        if here is None:
            away, left = away + 1, True
            if away > 2:
                break
        elif here != last:  # focus that stays put is moving on inside a frame
            away = 0
            if here in stops or here in found:
                if left or here in seen:
                    break
            else:
                found.append(here)
            seen.add(here)
        last = here
        page.keyboard.press("Shift+Tab")
        page.evaluate(A_FRAME)
    return found


def _keys_show(page, url, stops, paths, buttons, tries=3):
    """The paths among paths that a key on one of the Tab stops in stops shows: Enter, and Space
    too on a stop like a button. Each key is pressed from a fresh load. The stops like a button go
    first, since a menu a hover opens often has one beside its link that opens it from the keyboard."""
    shown = set()
    for stop in sorted(stops, key=lambda s: s not in buttons)[:tries]:
        for key in ("Enter", " ") if stop in buttons else ("Enter",):
            _fresh(page, url)
            try:
                _locate(page, stop).focus(timeout=2000)
                page.keyboard.press(key)
                page.wait_for_timeout(300)
                if exercise.same_url(page.url.split("#")[0], url.split("#")[0]):
                    shown.update(page.evaluate(SHOWN_NOW, paths))
            except Exception:
                pass  # the key took the page somewhere else, where what it shows can't be read
            if shown >= set(paths):
                return shown
    return shown


# Boxes that clip more than they show, have a wheel listener to scroll it, and hold no Tab stop,
# so no key can scroll them: the arrow keys scroll only what has focus or holds it.
WHEEL_BOXES = "stops => {" + HELPERS + _js("wheel_boxes")
PLACE = "path => {" + HELPERS + _js("place")


def _wheel_scrolls(page, url, path, noise=frozenset()):
    """Whether turning the mouse wheel over the element at path scrolls it or changes it."""
    _fresh(page, url)
    try:
        target = _locate(page, path)
        target.scroll_into_view_if_needed(timeout=2000)
        box = target.bounding_box(timeout=2000)
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        before = page.evaluate(PLACE, path)
        page.evaluate(NOTE_CHANGES)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(300)
        return page.evaluate(PLACE, path) != before or bool(_changed(page, noise))
    except Exception:
        return False
    finally:
        page.mouse.move(*exercise.PARK)


# Widgets that Tab reaches once and the arrow keys move through: a tab list, a menu, a toolbar,
# a list box. Each with the Tab stop in it and the item after the current one, for a click.
WIDGETS = "stops => {" + HELPERS + _js("widgets")
# Which of a widget's options and boxes are picked.
PICKED = "path => {" + HELPERS + _js("picked")
# The middle of an element, scrolled to the middle of the screen or of the box it scrolls in.
CENTER = "path => {" + HELPERS + _js("center")


def _split(page, widget, href, picked, changed):
    """[whether the page outside the widget changed, whether the widget did], from its address
    and picked options before and the elements changed since. Focus is left out: a click on an
    item focuses it with no handler."""
    inside = set(page.evaluate(INSIDE, [widget["path"], sorted(changed)]))
    return [page.url != href or bool(changed - inside),
            bool(inside) or page.evaluate(PICKED, widget["path"]) != picked]


def _widget_keys(page, url, widget, noise=frozenset()):
    """Whether the keys do in a widget what a click on its next item does: an arrow key to move
    there, then Enter, then Space. What has to change is the page outside the widget when the
    click changes that, else the widget itself. Yes when the click changes nothing, or when that
    can't be told."""
    _fresh(page, url)
    try:
        at = page.evaluate(CENTER, widget["item"])
        page.mouse.move(*at)
        href, picked = page.url, page.evaluate(PICKED, widget["path"])
        page.evaluate(NOTE_CHANGES)
        page.mouse.click(*at)
        page.wait_for_timeout(300)
        changed = _split(page, widget, href, picked, _changed(page, noise))
    except Exception:
        return True
    if not any(changed):
        return True
    part = changed.index(True)
    for arrow in ("ArrowRight", "ArrowDown"):
        _fresh(page, url)
        try:
            _locate(page, widget["stop"]).focus(timeout=2000)
            href, picked, seen = page.url, page.evaluate(PICKED, widget["path"]), set()
            page.evaluate(NOTE_CHANGES)
            for key in (arrow, "Enter", " "):
                page.keyboard.press(key)
                page.wait_for_timeout(200)
                seen |= _changed(page, noise)
                if _split(page, widget, href, picked, seen)[part]:
                    return True
        except Exception:
            return True
        finally:
            page.mouse.move(*exercise.PARK)
    return False


# How much is modal: elements made inert, modal dialogs, and shown aria-modal boxes. A page can
# have some as it loads, such as slides off the screen made inert, so what counts is a rise.
MODAL = "() => {" + HELPERS + _js("modal")


def _key_closes(page, url, path, base, tries=5):
    """Whether what Enter on the element at path opens closes with a key: Escape, or Enter on one
    of the first few things Tab reaches in it. Closed is back to base, the page's own MODAL count."""
    _fresh(page, url)
    try:
        _locate(page, path).focus(timeout=2000)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        for key in ["Escape"] + ["Tab", "Enter"] * tries:
            page.keyboard.press(key)
            page.wait_for_timeout(150)
            if page.evaluate(MODAL) <= base:
                return True
        return False
    except Exception:
        return True  # can't tell, so no finding


def _drags(page, url, path, noise=frozenset()):
    """Whether dragging the element at path 40 px to the right changes the page."""
    _fresh(page, url)
    try:
        target = _locate(page, path)
        target.scroll_into_view_if_needed(timeout=2000)
        box = target.bounding_box(timeout=2000)
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.evaluate(NOTE_CHANGES)
        page.mouse.down()
        page.mouse.move(x + 40, y, steps=8)
        page.mouse.up()
        page.wait_for_timeout(300)
        return bool(_changed(page, noise))
    except Exception:
        return False
    finally:
        page.mouse.move(*exercise.PARK)


ARROWS = ("ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End")


def _arrows_act(page, url, path, noise=frozenset()):
    """Whether any arrow, Page, Home or End key, pressed with the element at path focused,
    changes the page. When that can't be told, yes, so nothing is reported."""
    _fresh(page, url)
    try:
        _locate(page, path).focus(timeout=2000)
        page.evaluate(NOTE_CHANGES)
        for key in ARROWS:
            page.keyboard.press(key)
            page.wait_for_timeout(100)
            if _changed(page, noise):
                return True
        return False
    except Exception:
        return True


def _mouse_gated(page, url):
    """Controls that start disabled and that a moving mouse enables, where Tab and the same wait
    don't: a form that holds back its button until it sees a person, say. On a page of their own,
    which no pointer has been over."""
    other = page.context.browser.new_page(viewport=page.viewport_size)
    try:
        exercise.stay_on(other, url)
        other.goto(url, wait_until="load")
        other.evaluate(exercise.SETTLED, exercise.SETTLE_LIMIT_MS)
        disabled = other.evaluate(DISABLED)
        if not disabled:
            return []
        other.keyboard.press("Tab")
        other.wait_for_timeout(500)
        disabled = other.evaluate(STILL_DISABLED, disabled)
        size = other.viewport_size
        other.mouse.move(size["width"] / 2, size["height"] / 2)
        other.mouse.move(size["width"] / 2 + 20, size["height"] / 2 + 20, steps=4)
        other.wait_for_timeout(500)
        still = set(other.evaluate(STILL_DISABLED, disabled))
        return [path for path in disabled if path not in still]
    finally:
        other.close()


def keyboard_and_focus(page, width, url, max_tabs=MAX_TABS, max_focus=MAX_FOCUS, max_tries=MAX_TRIES):
    """[keyboard result, focus result] from one walk with Tab through the page, then a hover
    over each closed box Tab didn't open, and Enter and Space on each element like a button."""
    clicks = page.evaluate(CLICKABLE)
    targets = page.evaluate(TARGETS)
    skipped = page.evaluate(SKIPPED)
    hidden = page.evaluate(HIDDEN)
    base = page.evaluate(MODAL)
    proxy = {t["path"]: t["proxy"] for t in targets}
    # Each Tab stop's look with nothing focused, on the page as it loaded, to hold against its
    # look with focus. Blurring each one instead would run its blur handler. Only a field that
    # took focus as the page loaded is let go first, as a click elsewhere would.
    page.evaluate(LET_GO)
    plain = {}
    for t in targets[:max_focus]:
        try:
            plain[t["path"]] = _look_at(page, t["proxy"])
        except Exception:
            pass
    # The pictures scrolled the page and every box in it that scrolls, so the walk starts from a
    # fresh load: where Tab scrolls each stop to is part of what it measures.
    _fresh(page, url)
    blank = page.context.browser.new_page()  # about:blank, for comparing pictures
    # Tab can start partway down, after an autofocus field, so the walk goes on past the end of
    # the page, where focus leaves it, until it's back at the start.
    stops, trapped, unseen, checked, revealed, away = [], None, [], 0, set(), 0
    weak, later, moved = [], [], []

    def judge(here, shows):
        """AA passes when the part of the change outside the stop, or the part inside it, reaches
        RATIO against every colour touching it, or when the change reaches RATIO against how the
        stop looked before over a 2 px ring, as AAA asks."""
        if shows is None:
            unseen.append({"path": here, "why": "it looks the same with focus as without"})
            return
        if shows["changed"] is None:
            return  # it changed, by its style, but its pixels couldn't be compared
        beside = [r for r in (shows["outside"], shows["inside"]) if r is not None]
        changes = shows["shift"] >= RATIO and shows["changed"] >= shows["ring"]
        if not changes and not any(r >= RATIO for r in beside):
            near, what = (max(beside), "the colours beside it") if beside else (shows["shift"], "how it looks without focus")
            if shows["shift"] >= RATIO:  # a strong change, too small to count as a ring
                why = "its focus change reaches " + (
                    f"{_ratio(near)}:1 against the colours beside it, where AA asks {RATIO}:1, and " if beside else "") + (
                    f"{_ratio(shows['shift'])}:1 against how it looks without focus, but over "
                    f"{round(100 * shows['changed'] / shows['ring'])}% of a 2 px ring")
            else:
                why = f"its focus change reaches {_ratio(near)}:1 against {what}, and AA asks {RATIO}:1"
            unseen.append({"path": here, "why": why})
            return
        short = ([f"{_ratio(shows['shift'])}:1 against how it looks without focus"] if shows["shift"] < RATIO else []) + (
            [f"{round(100 * shows['changed'] / shows['ring'])}% of a 2 px ring"] if shows["changed"] < shows["ring"] else []) + (
            [f"it shows on {shows['sides']} of 4 sides"] if shows["sides"] is not None and shows["sides"] < 4 else [])
        if short:
            weak.append({"path": here, "why": "focus shows weakly: " + ", ".join(short)})
    # The stop the press before reached, the places inside it Tab went, how many stops there were
    # when focus last left the page, and whether a way out of a loop has already moved focus on.
    last, within, left, resume, freed = None, [], None, False, set()
    for _ in range(max_tabs):
        # Focus a script took back by itself since the last press, to a stop Tab reached before,
        # makes a loop from there, as a button that takes focus back a moment after losing it does.
        back = page.evaluate(ACTIVE) if last is not None and not resume else None
        if back is not None and back != last and back in stops:
            here = back
        else:
            if resume:
                resume = False
            else:
                page.keyboard.press("Tab")
                page.evaluate(A_FRAME)  # a script that takes focus back at once does it by then
            here = page.evaluate(ACTIVE)
        if here is None:
            away, last, left = away + 1, None, len(stops)
            if away > 2:
                break  # nothing on the page takes focus
            continue
        away = 0
        if here == last:
            # Tab can move on inside one element while the page's focus stays on it: through a
            # frame's own links, or a date field's day, month and year. Until it's back where it
            # was in there, or the presses run out, that isn't a trap.
            inside = page.evaluate(WITHIN)
            if (inside["kind"] and len(within) < INSIDE_LIMIT[inside["kind"]]
                    and (inside["at"] is None or inside["at"] not in within)):
                within.append(inside["at"])
                continue
        else:
            within = []
        last = here
        if here in stops:
            start = stops.index(here)
            if left is not None and start < left:
                break  # round the whole page: focus left it, and came back to a stop it reached before
            # Round some of them without leaving the page. As ACT's rules on keyboard traps have
            # it, that's a trap only when no key gets out of them either.
            loop = stops[start:]
            if here in freed:
                break  # back in a loop a key let go of before: the page holds focus there each time
            way = _way_out(page, loop)
            if way is None:
                trapped = {"path": here, "why": "Tab can't leave it" if len(loop) == 1 else
                           f"Tab goes round {_n(loop, 'element')} from here and never leaves them"}
                break
            if way in ("closed", "can't tell"):
                break  # Escape closed what held focus, such as a dialog the page waited behind
            if way == "Shift+Tab":
                stops += _walk_back(page, stops, max_tabs - len(stops))
                break  # the stops past the loop are reached backwards
            last, within, resume = None, [], True  # a key let go of focus, and Tab goes on from there
            freed.add(here)
            continue
        stops.append(here)
        if hidden:
            revealed.update(page.evaluate(SHOWN_NOW, [h["path"] for h in hidden]))
        if checked >= max_focus:
            continue
        # Judged where it ends up: a skip link that slides in on focus at the end of its
        # transition, as the screenshot would take it, and a card once the scroll to it ends, or a
        # carousel's slide once it has slid in, on the screen already or not.
        if not page.evaluate(ON_SCREEN) or page.evaluate(COVERED, proxy.get(here, here)):
            page.evaluate(HOLD)
            page.evaluate(RELEASE)
        page.evaluate(SCROLL_STILL, [SCROLL_LIMIT_MS, None])
        if not page.evaluate(ON_SCREEN):  # the browser scrolls a focused element into view
            seen = {"path": here, "why": "it's off the screen while it has focus"}
        elif ((over := page.evaluate(COVERED, proxy.get(here, here)))  # where the browser scrolled it
              and _paints_over(page, over, proxy.get(here, here), blank)):
            seen = {"path": here, "why": f"{over} covers it while it has focus"}
        elif here in plain:
            # A stop that didn't show as the page loaded was pictured by the box around it that
            # did. Once it shows with focus, as a carousel's slide does when Tab brings it in,
            # it's pictured by itself, and without focus on a fresh load, below.
            alone = proxy[here] != here and page.evaluate(SHOWN, here)
            seen, look = None, _look_at(page, here if alone else proxy[here])
        else:
            continue
        # A script can take focus away while the stop is measured, as one that takes it back a
        # moment after losing it does. Then what was measured isn't this stop with focus.
        if page.evaluate(ACTIVE) != here:
            continue
        checked += 1
        if seen:
            unseen.append(seen)
        elif alone or _moved(plain[here], look):
            moved.append((here, look, alone))
        else:
            shows = _shows(plain[here], look, blank)
            if shows is None and (around := _restyled(plain[here], look)):
                later.append((here, around, _look_at(page, around)))
            else:
                judge(here, shows)
    # What to probe is read here, on the page Tab walked, since each probe leaves the page as it
    # changed it, or still loading where it went.
    buttons = page.evaluate(BUTTONLIKE, stops)
    doubles = set(page.evaluate(DOUBLE, buttons))
    handles = page.evaluate(DRAGGABLE, stops)
    links = page.evaluate(LINKS_UNDER_KEYS, stops)
    wheels = page.evaluate(WHEEL_BOXES, stops)
    widgets = page.evaluate(WIDGETS, stops)
    fields = page.evaluate(TEXT_FIELDS, stops)
    places = set(page.evaluate(HREFS, stops))
    unheard = page.evaluate(ARIA_HIDDEN, stops)
    # A box around a stop that focus restyled, as :focus-within does, is pictured without focus on
    # a fresh load, as the stops were, since only then is nothing in it focused. So is a stop that
    # showed only with focus, scrolled to the middle as it was with focus, and the part of the page
    # a stop that focus resized or brought into the window was pictured over.
    if later or moved:
        _fresh(page, url)
        page.evaluate(LET_GO)
        for here, around, focused in later:
            try:
                judge(here, _shows(_look_at(page, around), focused, blank))
            except Exception:
                pass  # it can't be pictured without focus, so it can't be told
        for here, focused, alone in moved:
            try:
                before = _look_at(page, here) if alone else None
                if before is None or _moved(before, focused):
                    before = _look_over(page, focused)
                judge(here, _shows(before, focused, blank))
            except Exception:
                pass  # as above
    blank.close()
    # What changes by itself, as a clock does, is no sign that a key or a click did something.
    noise = _restless(page, url)
    # Each closed box Tab didn't open is hovered once, for everything in it. What the hover shows
    # is reachable when Enter or Space on a Tab stop in the same box shows it too, as a menu's
    # disclosure button does.
    hover_only, boxes = [], {}
    for h in hidden:
        if h["path"] not in revealed and h["box"]:
            boxes.setdefault(h["box"], []).append(h["path"])
    for box, paths in list(boxes.items())[:max_tries]:
        _fresh(page, url)
        try:
            _locate(page, box).hover(timeout=2000)
            page.wait_for_timeout(300)
            shown = page.evaluate(SHOWN_NOW, paths)
            near = page.evaluate(INSIDE, [box, stops]) if shown else []
        except Exception:
            continue
        keyed = _keys_show(page, url, near, shown, buttons) if near else set()
        how = "neither Tab nor Enter on a Tab stop in that box does" if near else "Tab never does"
        hover_only += [{"path": path, "why": f"hovering {box} shows it, and {how}"}
                       for path in shown if path not in keyed]
    # Enter first: on most buttons it works, and the click and the other keys aren't needed. What
    # Enter opens as a modal, with the rest of the page inert, has to close with a key too.
    # A key that can't be told to act or not counts as acting, so only a key seen to do nothing is
    # reported, and what Enter opens is read only while the page is still the one it was.
    dead, before = [], {t["path"] for t in targets}
    for path in buttons[:max_tries]:
        enter = _acts(page, url, path, "Enter", noise=noise)
        if enter:
            try:
                if not exercise.same_url(page.url, url):
                    continue
                opened = {t["path"] for t in page.evaluate(TARGETS)} - before
                modals = page.evaluate(MODAL)
            except Exception:
                continue
            # A dialog Enter closed lets Tab back into the page it waited in front of, which Enter
            # didn't open.
            if modals > base and not _key_closes(page, url, path, base):
                dead.append({"path": path, "why": "Enter opens a dialog that no key closes: not Escape, "
                             "and not Enter on anything Tab reaches in it"})
            elif opened and modals >= base and _opened_unreached(page, url, path, opened):
                what = "a link or control" if len(opened) == 1 else f"{len(opened)} links or controls"
                dead.append({"path": path, "why": f"Enter opens {what}, and neither Tab, Shift+Tab nor the "
                             "down arrow reaches them"})
        elif enter is False:
            mouse = ("a click" if _acts(page, url, path, noise=noise) else
                     "a double-click" if path in doubles and _acts(page, url, path, double=True, noise=noise) else None)
            if mouse and all(_acts(page, url, path, key, noise=noise) is False
                             for key in (" ", "ArrowDown", "Alt+ArrowDown")):
                dead.append({"path": path, "why": f"{mouse} works it, and Enter, Space and the down arrow don't"})
    # A link that Enter can't follow, under a key listener that cancels it.
    dead += [{"path": path, "why": "a click follows it, and Enter doesn't"}
             for path in links[:max_tries]
             if _acts(page, url, path, "Enter", noise=noise) is False and _acts(page, url, path, noise=noise)]
    # A box only the mouse wheel scrolls.
    dead += [{"path": path, "why": "a mouse wheel scrolls it, and nothing in it takes focus, so no key can"}
             for path in wheels[:5] if _wheel_scrolls(page, url, path, noise)]
    # A widget whose items a click works and the keys that move through it don't.
    dead += [{"path": w["path"], "why": f"a click on its item {w['text']!r} works it, and the arrow keys, "
              "Enter and Space don't"} for w in widgets[:5]
             if not _widget_keys(page, url, w, noise)]
    # Choices that typing shows, as in a search box that suggests.
    dead += [{"path": path, "why": "typing in it shows choices a mouse can pick, and neither the down arrow "
              "nor Tab gets to them"} for path in fields[:5]
             if _choices_unreached(page, url, path, noise=noise)]
    # Past a trap, Tab reaches nothing, and the trap is the finding.
    reached = {t["group"] for t in targets if t["group"] and t["path"] in stops}
    missed = [] if trapped else [t["path"] for t in targets if t["path"] not in stops and t["group"] not in reached]
    found = ([{"path": c["path"], "why": f"a mouse can {c['does']} it ({c['text']!r}), Tab can't reach it"}
              for c in clicks if c["href"] not in places]
             + [{"path": path, "why": "it takes focus, but Tab never reached it"} for path in missed]
             + [{"path": s["path"], "why": "it's a control, but tabindex=-1 takes it out of the Tab order"}
                for s in skipped if s["href"] not in places]
             + [{"path": path, "why": "Tab reaches it, but it's inside aria-hidden, which hides it from a screen "
                 "reader"} for path in unheard]
             + ([trapped] if trapped else [])
             + hover_only + dead
             + [{"path": path, "why": "dragging it works it, and no arrow, Page, Home or End key does"}
                for path in handles[:max_tries]
                if _drags(page, url, path, noise) and not _arrows_act(page, url, path, noise)]
             + [{"path": path, "why": "it stays disabled until a mouse moves, and Tab doesn't enable it"}
                for path in _mouse_gated(page, url)])
    keyboard = _result(width, "keyboard", found, f"Tab reached {len(stops)} elements, and all of "
                       "them can be left with Tab",
                       lambda f: f"{_n(f, 'element')} a keyboard can't use")
    more = f", {len(stops) - checked} not checked" if len(stops) > checked else ""
    # A weak stop passes at AA. It's counted here and named in "weak", since 2.4.13 at AAA fails it.
    more += f"; {len(weak)} show it weakly, short of what AAA asks" if weak else ""
    focus = _result(width, "focus", unseen, f"{checked} of {len(stops)} Tab stops show focus{more}",
                    lambda f: f"{len(f)} of {_n(checked, 'Tab stop')} don't show focus{more}")
    focus["weak"] = weak
    return [keyboard, focus]


def overflow(page, width):
    seen = page.evaluate(OVERFLOW)
    found = [{"path": c["path"], "why": f"its right edge is at {c['right']} px"} for c in seen["cut"]]
    if seen["scrollWidth"] > seen["width"] + 1 and not found:
        found = [{"path": "html", "why": f"the page is {seen['scrollWidth']} px wide"}]
    return _result(width, "overflow", found, f"everything fits in {seen['width']} px",
                   lambda f: f"{_n(f, 'element')} run past the right edge at {seen['width']} px")


VISIBLE_NOW = "path => {" + HELPERS + _js("visible_now")


def _hover_shows(page, path):
    """Whether a pointer over the element at path shows it, as a card that reveals a picture
    on hover does."""
    try:
        target = _locate(page, path)
        target.scroll_into_view_if_needed(timeout=2000)
        box = target.bounding_box(timeout=2000)
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(500)
        return page.evaluate(VISIBLE_NOW, path)
    except Exception:
        return False
    finally:
        page.mouse.move(*exercise.PARK)


# Shown elements with a picture as their background that the browser lays out inline, where the
# width and height their CSS sets don't apply, so the box can be too small to show it: a <span>
# sized for a logo, say. Rules are read from each sheet the page can read, in a media query too.
UNSIZED = "() => {" + HELPERS + _js("unsized")


def images(page, width, scale=SCALE):
    page.evaluate(SCROLL_THROUGH)
    page.wait_for_load_state("load")
    page.evaluate(exercise.SETTLED, exercise.SETTLE_LIMIT_MS)
    found, at = [], f"{scale:g}x"
    for box in page.evaluate(UNSIZED):
        (w, h), (dw, dh) = box["set"], box["drawn"]
        found.append({"path": box["path"], "why": f"its background {box['src']} is set to {w} by {h}, but "
                      f"it's laid out {box['display']}, where width and height don't apply, so it's drawn "
                      f"{dw}x{dh} px"})
    for img in page.evaluate(IMAGES, scale):
        what = f"its background {img['src']}" if img.get("background") else ""
        if img.get("unseen"):
            if not _hover_shows(page, img["path"]):
                found.append({"path": img["path"], "why": f"{img['src']} loaded, but opacity 0 keeps it from "
                              "ever showing, and nothing over the same spot shows instead"})
        elif img.get("replaced"):
            short = [v if len(v) <= 50 else v[:47] + "..." for v in (img["value"], img["later"][1])]
            found.append({"path": img["path"], "why": f'its {img["name"]} "{short[0]}" is replaced by the '
                          f'{img["later"][0]} "{short[1]}" after it, in the same block, so no picture is drawn'})
        elif img.get("broken") and img.get("inner"):
            found.append({"path": img["path"], "why": f"its SVG {img['inner']} links to {img['href']}, and an SVG "
                          "drawn as an image never loads what it links to"})
        elif img.get("invalid"):
            value = img["value"] if len(img["value"]) <= 60 else img["value"][:57] + "..."
            then = (f"its picture is drawn {img['size'][0]}x{img['size'][1]} px" if img.get("size")
                    else "draws no image")
            found.append({"path": img["path"], "why": f'its {img["name"]} "{value}" isn\'t valid CSS, '
                          f"so the browser drops it and {then}"})
        elif img.get("broken") and img.get("mask"):
            found.append({"path": img["path"], "why": f"its mask {img['src']} didn't load, so none of it paints"})
        elif img.get("broken"):
            choice = f", the {img['chosen']:g}x choice in its image-set()," if img.get("chosen") else ""
            found.append({"path": img["path"], "why": f"{what or img['src']}{choice} didn't load"})
        else:
            (w, h), (nw, nh) = img["natural"], img["needs"]
            crop = ", cropped to cover it," if img.get("cropped") else ","
            if img.get("inner"):
                what = f"the picture its SVG {img['inner']} holds"
            elif img.get("canvas"):
                what = "its canvas"
            found.append({"path": img["path"], "why": (f"{what + ' is ' if what else ''}drawn "
                          f"{img['width']}x{img['height']} px{crop} so it needs about {nw}x{nh} px "
                          f"at {at}; it has {w}x{h}")})
    return _result(width, "images", found, f"every image is sharp at {at}",
                   lambda f: f"{_n(f, 'image')} blurry at {at} or not loading")


def _moving_boxes(page, frames, cell=CELL):
    """[x, y, width, height] around each group of squares whose pixels changed from one frame
    to the next CHANGES times or more."""
    blank = page.context.browser.new_page()
    try:
        counts, cols = {}, None
        for a, b in zip(frames, frames[1:]):
            if a == b:
                continue
            seen = blank.evaluate(CELLS, [base64.b64encode(a).decode(), base64.b64encode(b).decode(),
                                          EDGE, cell, SEEN])
            if isinstance(seen, dict):
                cols = seen["cols"]
                for k in seen["cells"]:
                    counts[k] = counts.get(k, 0) + 1
    finally:
        blank.close()
    moving, boxes = {k for k, n in counts.items() if n >= CHANGES}, []
    while moving:  # squares that touch, corners too, are one box
        group, todo = [], [moving.pop()]
        while todo:
            k = todo.pop()
            group.append(k)
            row, col = divmod(k, cols)
            for r in (row - 1, row, row + 1):
                for c in (col - 1, col, col + 1):
                    if 0 <= c < cols and r * cols + c in moving:
                        moving.remove(r * cols + c)
                        todo.append(r * cols + c)
        rows, columns = [k // cols for k in group], [k % cols for k in group]
        x, y = min(columns) * cell, min(rows) * cell
        boxes.append([x, y, (max(columns) + 1) * cell - x, (max(rows) + 1) * cell - y])
    return boxes


def motion(page, width, limit_ms=MOTION_LIMIT_MS, watch_ms=WATCH_MS):
    page.wait_for_timeout(1000)
    found = [{"path": m["path"], "why": f"{m['name']} runs forever" if m["forever"]
              else f"{m['name']} runs {m['left']} ms more"}
             for m in page.evaluate(MOVING, limit_ms)]
    found += [{"path": m["path"], "why": f"its {m['name']} runs past {limit_ms / 1000:g} s"}
              for m in page.evaluate(SMIL, limit_ms)]
    # Past the 5 s mark, an element a script keeps restyling is moving too, and so are pixels
    # that keep changing on the first screen.
    page.wait_for_timeout(max(0, limit_ms - page.evaluate("performance.now()")))
    # A blinking caret isn't motion. Playwright hides it by restyling each field for each
    # picture, which the watch would count, so it's hidden once, before the watch starts.
    page.add_style_tag(content="* { caret-color: transparent !important; }")
    page.evaluate(WATCH)
    frames = []
    for i in range(watch_ms // FRAME_MS + 1):
        if i:
            page.wait_for_timeout(FRAME_MS)
        frames.append(page.screenshot(caret="initial"))
    named = [f["path"] for f in found]
    seen = page.evaluate(CHANGED, [_moving_boxes(page, frames), named])
    after = f"in {watch_ms / 1000:g} s, after the first {limit_ms / 1000:g} s"
    found += [{"path": m["path"], "why": f"a script changed its style or class {m['changes']} times {after}"}
              for m in seen["changing"] if m["path"] not in named]
    found += [{"path": m["path"], "why": f"its pixels kept changing {after}, in a {m['box'][0]}x{m['box'][1]} "
               "px box, with no animation, style or class change that shows why"} for m in seen["pixels"]]
    return _result(width, "motion", found, "with reduced motion, nothing runs on",
                   lambda f: f"with reduced motion asked for, {_n(f, 'element')} still moving")


def gates(url, widths, only=GATES, browser=None, serve=None, scale=SCALE):
    """A result for each width and gate: width, gate, status (pass, fail or error), detail
    and findings, each {"path", "why"}. With serve, a built folder, url is a path on it.
    Opens a Chromium unless given one. Raises GateError for a gate name it doesn't know."""
    unknown = [g for g in only if g not in GATES]
    if unknown:
        raise GateError(f"there is no gate named {unknown[0]!r}; the gates are {', '.join(GATES)}")
    if serve:
        with exercise.serving(serve) as base:
            return gates(base + "/" + url.lstrip("/"), widths, only, browser, None, scale)
    if browser is None:
        try:
            with exercise.chromium() as browser:
                return gates(url, widths, only, browser, None, scale)
        except exercise.ExerciseError as err:
            raise GateError(str(err)) from None
    def walk(page, width):
        # Overflow first, on the page as it loaded: the walk hovers, clicks and reloads.
        out = [overflow(page, width)] if "overflow" in only else []
        if {"keyboard", "focus"} & set(only):
            out = keyboard_and_focus(page, width, page.url) + out
        return out

    # Each page is opened fresh: one for Tab and overflow, one at the images' screen density,
    # and one that asks for reduced motion.
    runs = [(("keyboard", "focus", "overflow"), {}, walk),
            (("images",), {"device_scale_factor": scale}, lambda page, width: [images(page, width, scale)]),
            (("motion",), {"reduced_motion": "reduce"}, lambda page, width: [motion(page, width)])]
    results = []
    for width in widths:
        for names, options, run in runs:
            names = [name for name in names if name in only]
            if not names:
                continue
            page = None
            try:
                page = _open(browser, url, width, **options)
                results.extend(r for r in run(page, width) if r["gate"] in names)
            except Exception as err:
                results.extend({"width": width, "gate": name, "status": "error",
                                "detail": str(err).splitlines()[0], "findings": []} for name in names)
            finally:
                if page is not None:
                    page.close()
    return results


def write(path, url, results):
    design.write_json(Path(path), {"url": url, "results": results})


def report(results, shown=SHOWN_LIMIT):
    """The lines that follow the table: each failure's findings, at most shown per gate."""
    lines = []
    for r in results:
        if r["status"] != "pass" and r["findings"]:
            lines.append(f"\n--- {r['gate']} at {r['width']} px")
            for f in r["findings"][:shown]:
                lines.append(f"  {f['path']}: {f['why']}")
            if len(r["findings"]) > shown:
                lines.append(f"  and {len(r['findings']) - shown} more")
    return lines


def dumps(results):
    return json.dumps(results, indent=2)
