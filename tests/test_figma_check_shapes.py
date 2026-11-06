"""figma_check.py's reading of a Figma frame's lines, box edges, fills and icons, and its exact
comparisons, without a browser; and, where Playwright is installed, an icon's shape drawn in one."""
import importlib.util
import math
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "build-from-design" / "scripts" / "figma_check.py"


def load():
    spec = importlib.util.spec_from_file_location("figma_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def solid(r, g, b, opacity=1):
    return [{"type": "SOLID", "opacity": opacity, "color": {"r": r / 255, "g": g / 255, "b": b / 255, "a": 1}}]


def box(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def frame(*children, fills=None):
    return {"id": "0:1", "type": "FRAME", "name": "Frame", "absoluteBoundingBox": box(1000, 2000, 600, 400),
            "fills": fills if fills is not None else solid(17, 17, 19), "children": list(children)}


def chevron(nid, x, y):
    return {"id": nid, "type": "INSTANCE", "name": "Lucide Icons / chevron-up", "absoluteBoundingBox": box(x, y, 19.2, 19.2),
            "children": [{"id": nid + "v", "type": "VECTOR", "name": "Vector", "strokes": solid(255, 255, 255),
                          "strokeWeight": 1.2, "strokeCap": "ROUND", "strokeJoin": "ROUND",
                          "absoluteBoundingBox": box(x + 4.8, y + 7.2, 9.6, 4.8)}]}


class ShapesTest(unittest.TestCase):
    def setUp(self):
        self.fc = load()

    def test_a_line_is_where_figma_draws_it_blended_over_the_fill_behind(self):
        line = {"id": "1:1", "type": "LINE", "name": "divider", "strokes": solid(255, 255, 255, 0.1), "strokeWeight": 1,
                "strokeAlign": "CENTER", "absoluteBoundingBox": box(1136, 2392, 548, 0),
                "absoluteRenderBounds": box(1136, 2391, 548, 1)}
        lines, icons, fills = self.fc.frame_shapes(frame(line))
        self.assertEqual(lines[0]["box"], [136, 391, 548, 1])
        self.assertEqual([round(v) for v in lines[0]["color"]], [41, 41, 43])

    def test_a_line_figma_does_not_draw_is_not_checked(self):
        line = {"id": "1:1", "type": "LINE", "name": "hidden", "strokes": solid(255, 255, 255), "strokeWeight": 1,
                "absoluteBoundingBox": box(1040, 2340, 336, 0), "absoluteRenderBounds": None}
        self.assertEqual(self.fc.frame_shapes(frame(line))[0], [])

    def test_an_outside_stroke_is_drawn_one_pixel_outside_the_box_with_its_corners_left_out(self):
        card = {"id": "2:1", "type": "FRAME", "name": "card", "absoluteBoundingBox": box(1112, 2296, 596, 216),
                "fills": solid(17, 17, 19), "strokes": solid(255, 255, 255, 0.1), "strokeWeight": 1,
                "strokeAlign": "OUTSIDE", "cornerRadius": 12, "children": []}
        lines, _, _ = self.fc.frame_shapes(frame(card))
        sides = {l["name"].split()[-2]: l["box"] for l in lines}
        self.assertEqual(sides["top"], [124, 295, 572, 1])  # 598 wide outside, less two 13px corners
        self.assertEqual(sides["left"], [111, 308, 1, 192])
        self.assertEqual(sides["bottom"][1], 512)
        self.assertEqual(sides["right"][0], 708)

    def test_an_inside_stroke_is_drawn_inside_the_box(self):
        card = {"id": "2:1", "type": "FRAME", "name": "card", "absoluteBoundingBox": box(1112, 2296, 596, 216),
                "strokes": solid(255, 255, 255), "strokeWeight": 1, "strokeAlign": "INSIDE", "children": []}
        sides = {l["name"].split()[-2]: l["box"] for l in self.fc.frame_shapes(frame(card))[0]}
        self.assertEqual(sides["top"][1], 296)
        self.assertEqual(sides["right"][0], 707)

    def test_the_icon_is_the_instance_not_the_frame_wrapped_round_it(self):
        wrap = {"id": "3:1", "type": "FRAME", "name": "Frame 1", "absoluteBoundingBox": box(1334, 2132, 24, 24),
                "children": [chevron("3:2", 1336.4, 2134.4)]}
        _, icons, _ = self.fc.frame_shapes(frame(wrap))
        self.assertEqual([i["id"] for i in icons], ["3:2"])
        self.assertAlmostEqual(icons[0]["box"][0], 336.4, places=4)
        self.assertEqual(icons[0]["stroke"], {"weight": 1.2, "cap": "round", "join": "round"})
        self.assertEqual(icons[0]["rotation"], 0)

    def test_a_fill_is_read_where_no_child_covers_it(self):
        card = {"id": "4:1", "type": "FRAME", "name": "card", "absoluteBoundingBox": box(1100, 2100, 200, 100),
                "fills": solid(24, 24, 27), "children": [{"id": "4:2", "type": "TEXT", "name": "t", "characters": "x",
                                                          "absoluteBoundingBox": box(1124, 2124, 152, 52)}]}
        fills = self.fc.frame_shapes(frame(card))[2]
        spot = next(f for f in fills if f["id"] == "4:1")
        x, y = spot["at"]
        self.assertFalse(124 <= x <= 276 and 124 <= y <= 176)
        self.assertEqual(spot["color"], [24, 24, 27])

    def test_text_values_are_not_rounded(self):
        t = {"id": "5:1", "type": "TEXT", "name": "t", "characters": "Hello", "absoluteBoundingBox": box(1336.4, 2134.4, 19.2, 24),
             "style": {"fontSize": 16, "fontWeight": 400, "lineHeightPx": 24, "letterSpacing": -0.4}}
        texts, _ = self.fc.frame_texts(frame(t))
        self.assertAlmostEqual(texts[0]["x"], 336.4, places=4)

    def test_lengths_match_only_within_a_layout_step_and_type_values_only_exactly(self):
        self.assertTrue(self.fc.same(336.40625, 336.4))
        self.assertFalse(self.fc.same(337, 336.4))
        self.assertFalse(self.fc.equal(-0.39, -0.4))
        self.assertTrue(self.fc.equal(28.799999237060547, 28.8))

    def test_a_turned_icon_s_shape_goes_through_the_turn(self):
        d = {"size": [19.1875, 19.1875], "centre": [346.0, 144.0], "rotation": -180}
        self.fc.place_glyph({"vb": [0, 0, 19.2, 19.2], "par": "none", "bbox": [4.8, 7.2, 9.6, 4.8],
                             "stroke": {"weight": 1.2, "cap": "round", "join": "round"}}, d)
        self.assertAlmostEqual(d["glyph"][0], 341.2, places=1)
        self.assertAlmostEqual(d["glyph"][1], 141.6, places=1)


# A chevron-up drawn as a 2px stroke with butt caps and a mitred join, as the polygon Figma fills
# for it (its strokeGeometry), in the vector's own 12 x 6 space: the line runs 0,6 to 6,0 to 12,6.
R = 2 ** -0.5
CHEVRON_UP = [(-R, 6 - R), (6, -2 * R), (12 + R, 6 - R), (12 - R, 6 + R), (6, 2 * R), (R, 6 + R)]


def polygon(points):
    return "M" + "L".join(f"{x} {y}" for x, y in points) + "Z"


def geo_icon(nid, x, y, vector_rt, vector_size, points, glyph=None):
    """A 24px icon instance at x, y holding one stroked vector whose paths a geometry=paths read gave."""
    gx, gy, gw, gh = glyph or (x + 6, y + 9, 12, 6)
    return {"id": nid, "type": "INSTANCE", "name": "Icon / chevron-up", "absoluteBoundingBox": box(x, y, 24, 24),
            "relativeTransform": [[1, 0, x - 1000], [0, 1, y - 2000]], "size": {"x": 24, "y": 24}, "clipsContent": True,
            "fills": [], "strokes": [], "fillGeometry": [{"path": "M0 0L24 0L24 24L0 24L0 0Z", "windingRule": "NONZERO"}],
            "children": [{"id": nid + "v", "type": "VECTOR", "name": "Vector", "strokes": solid(17, 17, 19), "strokeWeight": 2,
                          "strokeCap": "NONE", "strokeJoin": "MITER", "absoluteBoundingBox": box(gx, gy, gw, gh),
                          "relativeTransform": vector_rt, "size": {"x": vector_size[0], "y": vector_size[1]},
                          "fillGeometry": [], "strokeGeometry": [{"path": polygon(points), "windingRule": "NONZERO"}]}]}


def numbers(d):
    return [float(v) for v in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", d)]


def draw(fc, shapes, size=24):
    """Figma's shapes for an icon as the mask the check compares, (width, rows), filled here with
    the standard library alone: a pixel is in when its centre is inside one of the polygons. Only
    M, L and Z paths, which these tests use."""
    S, M = fc.SHAPE_SCALE, fc.SHAPE_MARGIN
    w = h = (size + 2 * M) * S
    rows = [0] * h
    for s in shapes:
        for part in s["d"].split("Z"):
            v = numbers(part)
            pts = [((x + M) * S, (y + M) * S) for x, y in zip(v[::2], v[1::2])]
            if len(pts) < 3:
                continue
            edges = list(zip(pts, pts[1:] + pts[:1]))
            for y in range(max(0, int(min(p[1] for p in pts))), min(h, int(max(p[1] for p in pts)) + 1)):
                c = y + 0.5
                xs = sorted(x0 + (c - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in edges if (y0 <= c) != (y1 <= c))
                for a, b in zip(xs[::2], xs[1::2]):
                    lo, hi = max(0, math.ceil(a - 0.5)), min(w, math.floor(b - 0.5) + 1)
                    if hi > lo:
                        rows[y] |= ((1 << (hi - lo)) - 1) << (w - hi)
    return w, rows


def shift(m, dx, dy):
    """A mask moved dx pixels right and dy down."""
    w, rows = m
    return w, [0] * dy + [r >> dx for r in rows[:len(rows) - dy]]


class IconShapeTest(unittest.TestCase):
    def setUp(self):
        self.fc = load()

    def icon(self, *args, **kw):
        _, icons, _ = self.fc.frame_shapes(frame(geo_icon("6:1", *args, **kw)))
        self.assertEqual(len(icons), 1)
        return icons[0]

    def test_figma_s_paths_are_moved_into_the_icon_s_box(self):
        icon = self.icon(1336, 2134, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)
        self.assertIsNone(icon["shape_why"])
        self.assertEqual(len(icon["shape"]), 1)  # the instance's box has no visible fill, so only the stroke is drawn
        got = numbers(icon["shape"][0]["d"])
        want = [v + (6 if k % 2 == 0 else 9) for k, v in enumerate(numbers(polygon(CHEVRON_UP)))]
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, places=5)
        self.assertEqual(icon["shape"][0]["clips"], ["M 0 0 L 24 0 L 24 24 L 0 24 Z"])  # the instance clips

    def test_a_path_moved_or_scaled_into_the_box_is_the_same_shape_and_a_mirrored_one_is_not(self):
        plain = self.icon(1336, 2134, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)
        moved = self.icon(1100, 2210, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)  # the icon elsewhere in the frame
        half = [(x / 2, y / 2) for x, y in CHEVRON_UP]
        scaled = self.icon(1336, 2134, [[2, 0, 6], [0, 2, 9]], (6, 3), half)  # drawn half size, scaled up by its transform
        mirrored = self.icon(1336, 2134, [[1, 0, 6], [0, -1, 15]], (12, 6), CHEVRON_UP)  # flipped top to bottom
        self.assertEqual(mirrored["glyph"], plain["glyph"])  # the boxes can't tell them apart
        base = draw(self.fc, plain["shape"])
        for name, icon in (("moved", moved), ("scaled", scaled)):
            same, area, _ = self.fc.same_shape(base, draw(self.fc, icon["shape"]))
            self.assertTrue(same, f"{name}: {area}px² off")
        same, area, where = self.fc.same_shape(base, draw(self.fc, mirrored["shape"]))
        self.assertFalse(same)
        self.assertGreater(area, 10)

    def test_shapes_match_to_one_layout_step_and_no_further(self):
        base = draw(self.fc, self.icon(1336, 2134, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)["shape"])
        self.assertTrue(self.fc.same_shape(base, shift(base, 1, 0))[0])  # 1/64 px across
        self.assertTrue(self.fc.same_shape(base, shift(base, 1, 1))[0])  # and 1/64 px down
        same, area, where = self.fc.same_shape(base, shift(base, 2, 1))  # 2/64 px across
        self.assertFalse(same)
        self.assertLess(area, 1)
        # the pixels off run the length of the stroke, so their box is the stroke's, give or take a step
        M, xs, ys = self.fc.SHAPE_MARGIN, [x + 6 for x, _ in CHEVRON_UP], [y + 9 for _, y in CHEVRON_UP]
        for got, want in zip(where, (min(xs), min(ys), max(xs), max(ys))):
            self.assertAlmostEqual(got, M + want, delta=0.1, msg=where)

    def test_a_mask_from_the_browser_reads_its_rows_left_pixel_first(self):
        import base64
        # 10 pixels wide, so each row is 2 bytes with 6 bits left over; row 0 has pixel 0, row 1 pixels 8 and 9
        packed = {"width": 10, "height": 2, "bits": base64.b64encode(bytes([0b10000000, 0, 0, 0b11000000])).decode()}
        w, rows = self.fc.mask(packed)
        self.assertEqual((w, rows), (10, [1 << 9, 0b11]))

    def test_an_icon_without_figma_s_paths_did_not_run(self):
        node = geo_icon("6:1", 1336, 2134, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)
        del node["children"][0]["strokeGeometry"]
        _, icons, _ = self.fc.frame_shapes(frame(node))
        self.assertIsNone(icons[0]["shape"])
        self.assertIn("geometry=paths", icons[0]["shape_why"])
        ok, _, got = self.fc.shape_check(icons[0], {"found": True}, page=None, text="<svg/>")
        self.assertIsNone(ok)
        self.assertTrue(got.startswith("DID NOT RUN: "))
        rep = {"could_not_run": [], "met": 90, "total": 91, "did_not_run": 1}
        self.assertEqual(self.fc.exit_code(rep), 2)
        self.assertEqual(self.fc.status(rep), "1 did not run")

    def test_an_icon_whose_transform_is_missing_did_not_run(self):
        node = geo_icon("6:1", 1336, 2134, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)
        del node["children"][0]["relativeTransform"]
        _, icons, _ = self.fc.frame_shapes(frame(node))
        self.assertIsNone(icons[0]["shape"])
        self.assertIn("transform", icons[0]["shape_why"])

    def test_figma_s_path_commands_are_moved_exactly(self):
        m = [[2, 0, 1], [0, -1, 3]]
        self.assertEqual(self.fc.place_path("M0 0L1 2Q2 3 4 5C1 1 2 2 3 3Z", m), "M 1 3 L 3 1 Q 5 0 9 -2 C 3 2 5 1 7 0 Z")
        self.assertIsNone(self.fc.place_path("M0 0A1 1 0 0 1 2 2", m))  # an arc, which REST geometry never writes
        self.assertIsNone(self.fc.place_path("m0 0l1 1", m))


def has_browser():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(has_browser(), "needs Playwright and its Chromium")
class IconShapeInBrowserTest(unittest.TestCase):
    """The check's own drawing in Chromium: Figma's chevron-up polygon against an SVG file."""

    def svg(self, view, body):
        return (f'<svg width="24" height="24" viewBox="{view}" fill="none" xmlns="http://www.w3.org/2000/svg">{body}</svg>')

    def path(self, d, width=2):
        return f'<path d="{d}" stroke="#111113" stroke-width="{width}" stroke-linecap="butt" stroke-linejoin="miter"/>'

    def test_an_svg_path_moved_or_scaled_into_the_box_matches_and_a_mirrored_one_does_not(self):
        from playwright.sync_api import sync_playwright
        fc = load()
        _, icons, _ = fc.frame_shapes(frame(geo_icon("6:1", 1336, 2134, [[1, 0, 6], [0, 1, 9]], (12, 6), CHEVRON_UP)))
        f = icons[0]
        cases = {
            "drawn as in Figma": (self.svg("0 0 24 24", self.path("M6 15L12 9L18 15")), [1, 0, 0, 1], True),
            "moved into the box": (self.svg("0 0 24 24", '<g transform="translate(6 9)">' + self.path("M0 6L6 0L12 6") + "</g>"), [1, 0, 0, 1], True),
            "scaled into the box": (self.svg("0 0 48 48", self.path("M12 30L24 18L36 30", 4)), [1, 0, 0, 1], True),
            "chevron-down turned 180 degrees": (self.svg("0 0 24 24", self.path("M6 9L12 15L18 9")), [-1, 0, 0, -1], True),
            "mirrored": (self.svg("0 0 24 24", self.path("M6 9L12 15L18 9")), [1, 0, 0, 1], False),
        }
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            page = br.new_page()
            try:
                for name, (text, linear, want) in cases.items():
                    d = {"found": True, "size": [24, 24], "box": [336, 134, 24, 24], "linear": linear}
                    ok, _, got = fc.shape_check(f, d, page, text)
                    self.assertIs(ok, want, f"{name}: {got}")
            finally:
                br.close()


# figma_client.py reads FIGMA_CLIENT_DIR as its own state, cache and log folder. A state folder can
# hold anything, so the one planted there writes a mark if it is ever run.
PLANTED = ("import os\nclass NoToken(Exception):\n    pass\ndef get(path, **kw):\n"
           "    open(os.path.join(os.path.dirname(__file__), 'planted-client-ran'), 'w').write(path)\n"
           "    return {'from': 'the state folder'}\n")
PLUGIN = "class NoToken(Exception):\n    pass\ndef get(path, **kw):\n    return {'from': 'the plugin'}\n"


class ClientTest(unittest.TestCase):
    """Where the check finds the plugin's Figma client: in the plugin's tools/ folder only."""

    def call(self, env):
        """figma_get with this environment, from a clean import state, put back afterwards."""
        fc = load()
        module, path = sys.modules.pop("figma_client", None), list(sys.path)
        try:
            with mock.patch.dict(os.environ, env):
                return fc.figma_get("files/KEY/nodes?ids=1:1")
        finally:
            sys.modules.pop("figma_client", None)
            if module is not None:
                sys.modules["figma_client"] = module
            sys.path[:] = path

    def test_a_state_folder_in_figma_client_dir_is_never_read_as_the_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, tools = Path(tmp, "state"), Path(tmp, "plugin", "tools")
            state.mkdir()
            tools.mkdir(parents=True)
            (state / "bucket.json").write_text("{}", encoding="utf-8")
            (state / "figma_client.py").write_text(PLANTED, encoding="utf-8")
            (tools / "figma_client.py").write_text(PLUGIN, encoding="utf-8")
            before = sorted(str(p.relative_to(state)) for p in state.rglob("*"))
            got = self.call({"FIGMA_CLIENT_DIR": str(state), "CLAUDE_PLUGIN_ROOT": str(tools.parent)})
            self.assertEqual(got, {"from": "the plugin"})
            self.assertEqual(sorted(str(p.relative_to(state)) for p in state.rglob("*")), before)  # nothing written there

    def test_without_claude_plugin_root_the_client_is_the_one_three_folders_up(self):
        with tempfile.TemporaryDirectory() as state:
            fc = load()
            with mock.patch.dict(os.environ, {"FIGMA_CLIENT_DIR": state}):
                os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
                self.assertEqual(Path(fc.client_dir()), ROOT / "tools")


if __name__ == "__main__":
    unittest.main()
