"""product-os design exercise: a build that has every state the design draws passes, and
each planted build that lacks one fails on that state and no other.

The design is tests/design_payload.py's. The builds are small pages written here. Skipped
without Playwright and its Chromium.
"""
import io
import json
import tempfile
import threading
import unittest
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from product_os import design, exercise
from product_os.cli import main

from design_payload import box, go, node, payload, reaction

GOOD = """<!doctype html><meta name=viewport content="width=device-width">
<style>
  body { margin: 0; font: 16px sans-serif; }
  .button { background: #0055ff; color: #fff; border: 0; padding: 12px 24px; margin: 24px; }
  .button:hover { background: #0033aa; }
  .button:focus-visible { outline: 2px solid #111; outline-offset: 2px; }
  .panel { display: none; }
  .menu.open .panel { display: block; }
  #search { display: none; }
  .searching #search { display: block; }
</style>
<main data-figma-node="1:2">
  <h1>Shop</h1>
  <button class=button data-figma-node="1:5"><span data-figma-node="I1:5;10:9"
    onclick="location.hash = 'pricing'">Get started</span></button>
  <a data-figma-node="1:6" href="https://example.com/docs">Docs</a>
  <div class=menu data-figma-node="1:7" onclick="this.classList.toggle('open')">Menu
    <div class=panel>Orders</div></div>
  <button class=button disabled data-figma-node="1:8">Later</button>
  <div id=search>Search</div>
</main>
<script>
  addEventListener("keydown", e => { if (e.key === "k") document.body.classList.add("searching"); });
</script>
"""

# Each planted build lacks one state: its changes to GOOD, the state it should fail on, and how.
PLANTED = {
    "no hover style": ([(".button:hover { background: #0033aa; }", "")], ("1:5", "hover"),
                       "no change"),
    "a div, not a button": ([('<button class=button data-figma-node="1:5">',
                              '<div class=button data-figma-node="1:5">'),
                             ("</span></button>", "</span></div>")], ("1:5", "focus"), "not reached"),
    "the wrong link": ([('href="https://example.com/docs"', 'href="https://example.com/doc"')],
                       ("1:6", "click"), "wrong link"),
    "no link": ([('<a data-figma-node="1:6" href="https://example.com/docs">Docs</a>',
                  '<span data-figma-node="1:6">Docs</span>')], ("1:6", "click"), "no link"),
    "a menu that doesn't open": ([(" onclick=\"this.classList.toggle('open')\"", "")],
                                 ("1:7", "click"), "no change"),
    "an unmarked node with other copy": ([('class=menu data-figma-node="1:7"', "class=menu"),
                                          ("')\">Menu\n", "')\">More\n")], ("1:7", "click"), "not found"),
    "a label that goes nowhere": ([("\n    onclick=\"location.hash = 'pricing'\"", "")],
                                  ("I1:5;10:9", "click"), "no change"),
    "no key reaction": ([('addEventListener("keydown"', 'removeEventListener("keydown"')],
                        ("1:2", "key"), "no change"),
}


def timed_payload():
    """The payload with a textless Live dot, 1:9, that the design changes after a timeout."""
    out = payload()
    dot = reaction("1:9", "Live dot", {"type": "AFTER_TIMEOUT", "timeout": 0.8},
                   go("CHANGE_TO", "1:9"))
    tree = out["frame"]["node"]["document"]
    tree["children"].append(node("1:9", "FRAME", "Live dot", box(1800, 600, 16, 16),
                                 interactions=[{k: dot[k] for k in ("trigger", "actions")}]))
    out["frame"]["reactions"].append(dot)
    return out


PULSE = """<style>@keyframes pulse { 50% { opacity: 0.3 } }
  .dot { display: inline-block; width: 16px; height: 16px; background: #0a0; }
  .pulse { animation: pulse 1s infinite; }</style>"""
TIMED = {  # the dot's markup, and what the Live dot's timed state should get
    "an animated dot": ('<span class="dot pulse" data-figma-node="1:9"></span>', "responds"),
    # once, at the design's timeout of 0.8 s after the page loads
    "a dot a script changes": ('<span class=dot data-figma-node="1:9"></span><script>setTimeout('
                               '() => document.querySelector(".dot").style.background = "#060", '
                               '800)</script>', "responds"),
    "a dot that never moves": ('<span class=dot data-figma-node="1:9"></span>', "no change"),
    "a still dot beside a pulse": ('<span class=dot data-figma-node="1:9"></span>'
                                   '<span class="dot pulse"></span>', "no change"),
    "an unmarked dot": ('<span class="dot pulse"></span>', "not found"),
}


def plant(changes):
    html = GOOD
    for old, new in changes:
        assert html.count(old) == 1, f"the plant has to change the page once: {old!r}"
        html = html.replace(old, new)
    return html


class ExerciseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        try:
            cls.browser = cls.stack.enter_context(exercise.chromium())
        except exercise.ExerciseError as err:
            raise unittest.SkipTest(str(err)) from None
        cls.tmp = cls.stack.enter_context(tempfile.TemporaryDirectory())
        cls.root = Path(cls.tmp)
        cls.baseline = cls.root / "design"
        design.save_frame(cls.baseline, payload())

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def build(self, name, html):
        path = self.root / f"{name.replace(' ', '-')}.html"
        path.write_text(html, encoding="utf-8")
        return path.as_uri()

    def results(self, url, **options):
        return {(r["node"], r["do"]): r
                for r in exercise.exercise(self.baseline, url, browser=self.browser, **options)
                if r["do"] != "none"}

    def command(self, url, *args, baseline=None):
        """(exit code, output) of product-os design exercise, on this class's browser:
        Playwright can't start a second one in the same thread."""
        out = io.StringIO()
        browser = mock.patch.object(exercise, "chromium", lambda: nullcontext(self.browser))
        with redirect_stdout(out), redirect_stderr(out), browser:
            code = main(["design", "exercise", url, "--baseline", str(baseline or self.baseline),
                         *args])
        return code, out.getvalue()

    def test_the_good_build_responds_in_every_exercised_state(self):
        evidence = self.root / "evidence"
        code, out = self.command(self.build("good", GOOD), "--evidence", str(evidence))
        self.assertEqual(code, 0, out)
        self.assertIn("6 of 6 exercised states responded; 2 states not exercised.", out)
        saved = json.loads((evidence / "results.json").read_text(encoding="utf-8"))["results"]
        self.assertEqual([r["status"] for r in saved].count("responds"), 6)
        hover = next(r for r in saved if r["do"] == "hover")
        self.assertEqual(len(hover["evidence"]), 2)
        self.assertTrue(all(Path(p).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
                            for p in hover["evidence"]))

    def test_each_planted_build_fails_on_its_own_state(self):
        good = {key: r["status"] for key, r in self.results(self.build("good", GOOD)).items()}
        self.assertEqual(set(good.values()), {"responds"})
        for name, (changes, state, status) in PLANTED.items():
            with self.subTest(name):
                got = self.results(self.build(name, plant(changes)), settle_ms=150)
                self.assertEqual(got[state]["status"], status, got[state]["detail"])
                others = {key: r["status"] for key, r in got.items() if key != state}
                self.assertEqual(set(others.values()), {"responds"}, others)

    def test_a_planted_build_fails_the_command(self):
        code, out = self.command(self.build("planted", plant(PLANTED["no hover style"][0])))
        self.assertEqual(code, 1, out)
        self.assertIn("5 of 6 exercised states responded", out)

    def test_an_animation_that_loops_elsewhere_isnt_a_response(self):
        noise = ("<style>@keyframes blink { 50% { opacity: 0.2; transform: scale(0.8) } }\n"
                 "  .noise { width: 300px; height: 120px; background: #e33; "
                 "animation: blink 0.15s infinite; }</style>\n<div class=noise></div>\n</main>")
        dead = {("1:7", "click"): PLANTED["a menu that doesn't open"][0],
                ("1:2", "key"): PLANTED["no key reaction"][0]}
        for state, changes in dead.items():
            with self.subTest(state):
                html = plant(changes).replace("</main>", noise)
                for run in range(3):
                    got = self.results(self.build(f"noise-{run}", html))
                    self.assertEqual(got[state]["status"], "no change", f"run {run + 1}")
        got = self.results(self.build("noise-good", GOOD.replace("</main>", noise)))
        self.assertEqual({r["status"] for r in got.values()}, {"responds"})

    def test_a_timed_state_passes_only_when_its_own_node_moves(self):
        folder = self.root / "timed"
        design.save_frame(folder, timed_payload())
        for name, (markup, status) in TIMED.items():
            with self.subTest(name):
                html = GOOD.replace("</main>", f"{PULSE}{markup}\n</main>")
                got = {(r["node"], r["do"]): r for r in exercise.exercise(
                    folder, self.build(name, html), browser=self.browser, wait_s=1.5)}
                self.assertEqual(got[("1:9", "wait")]["status"], status,
                                 got[("1:9", "wait")]["detail"])

    def test_an_accepted_state_is_reported_with_its_reason_and_passes(self):
        hover = next(s for s in design.plan_states(self.baseline) if s.do == "hover")
        accept = self.root / "accepted.json"
        accept.write_text(json.dumps([
            {"node": hover.node, "state": hover.state, "why": "hover is the focus look, by ruling"},
            {"node": "1:7", "state": "Open=True", "why": "kept from an old ruling"}]),
            encoding="utf-8")
        url = self.build("accepted", plant(PLANTED["no hover style"][0]))
        code, out = self.command(url, "--accept", str(accept))
        self.assertEqual(code, 0, out)
        self.assertIn("5 of 6 exercised states responded, 1 accepted", out)
        self.assertIn("no change, accepted: hover is the focus look, by ruling", out)
        self.assertIn("but not needed: 1:7 Open=True", out)
        accept.write_text(json.dumps([{"node": "1:5", "state": hover.state}]), encoding="utf-8")
        self.assertEqual(self.command(url, "--accept", str(accept))[0], 2)

    def test_a_selector_file_finds_nodes_the_build_doesnt_mark(self):
        unmarked = GOOD.replace('class=menu data-figma-node="1:7"', "class=menu id=menu")
        got = self.results(self.build("unmarked", unmarked), selectors={"1:7": "#menu"})
        self.assertEqual(got[("1:7", "click")]["status"], "responds")

    def test_a_node_the_build_doesnt_mark_is_found_by_its_text(self):
        unmarked = GOOD.replace(' data-figma-node="1:5"', "").replace(' data-figma-node="1:7"', "")
        got = self.results(self.build("by-text", unmarked))
        self.assertEqual({k: r["status"] for k, r in got.items()},
                         {k: "responds" for k in got}, "found by the texts Get started and Menu")
        missing = unmarked.replace("Get started", "Start now")
        got = self.results(self.build("other-copy", missing))
        self.assertEqual(got[("1:5", "hover")]["status"], "not found", "the build's copy differs")

    def test_a_built_folder_is_served_and_exercised(self):
        site = self.root / "site"
        (site / "shop").mkdir(parents=True)
        (site / "shop" / "index.html").write_text(GOOD, encoding="utf-8")
        code, out = self.command("/shop/", "--serve", str(site))
        self.assertEqual(code, 0, out)
        self.assertIn("6 of 6 exercised states responded", out)

    def test_a_click_that_opens_another_site_responds_and_the_site_isnt_loaded(self):
        hits = []

        class Elsewhere(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"elsewhere")

            def log_message(self, *args):
                pass

        other = ThreadingHTTPServer(("127.0.0.1", 0), Elsewhere)
        threading.Thread(target=other.serve_forever, daemon=True).start()
        self.addCleanup(other.server_close)
        self.addCleanup(other.shutdown)
        away = f"http://127.0.0.1:{other.server_address[1]}/pricing"
        site = self.root / "site-away"
        site.mkdir()
        (site / "index.html").write_text(GOOD.replace("location.hash = 'pricing'",
                                                      f"location.href = '{away}'"),
                                         encoding="utf-8")
        with exercise.serving(site) as base:
            got = self.results(base + "/")[("I1:5;10:9", "click")]
        self.assertEqual((got["status"], got["detail"]),
                         ("responds", f"it opens {away}, which isn't followed"))
        self.assertEqual(hits, [], "the other site was loaded")

    def test_nothing_exercised_is_not_a_pass(self):
        folder = self.root / "disabled-only"
        only = payload()
        only["frame"]["reactions"] = []
        only["frame"]["instances"] = only["frame"]["instances"][2:]
        design.save_frame(folder, only)
        code, out = self.command(self.build("good", GOOD), baseline=folder)
        self.assertEqual(code, 1, out)
        self.assertIn("No state was exercised, so nothing passed.", out)


class SameUrlTest(unittest.TestCase):
    def test_a_trailing_slash_and_the_host_case_dont_matter(self):
        self.assertTrue(exercise.same_url("https://Example.com/docs/", "https://example.com/docs"))
        self.assertTrue(exercise.same_url("https://example.com", "https://example.com/"))
        self.assertFalse(exercise.same_url("https://example.com/doc", "https://example.com/docs"))
        self.assertFalse(exercise.same_url("https://example.com/docs?a=1", "https://example.com/docs"))


if __name__ == "__main__":
    unittest.main()
