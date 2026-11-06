"""figma_check.py's reading of a Figma frame's lines, box edges, fills and icons, and its exact
comparisons, without a browser."""
import importlib.util
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
