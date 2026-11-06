"""figma_check.py --frames: the lines a build-from-design report opens with, printed without a
browser, so they're there even where the check can't run."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "build-from-design" / "scripts" / "figma_check.py"


def load():
    spec = importlib.util.spec_from_file_location("figma_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frame(fid, name, width):
    return {"id": fid, "type": "FRAME", "name": name,
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": width, "height": 400}, "children": []}


class FramesTest(unittest.TestCase):
    def run_frames(self, cached, ids, figma_get=None):
        check = load()
        with tempfile.TemporaryDirectory() as cache:
            for doc in cached:
                Path(check.cache_file(cache, "KEY", doc["id"])).write_text(json.dumps(doc), encoding="utf-8")
            args = ["--frames", "--file", "KEY", "--cache", cache]
            for fid in ids:
                args += ["--frame", fid]
            out = io.StringIO()
            with redirect_stdout(out), mock.patch.object(check, "figma_get", figma_get or self.fail):
                code = check.main(args)
        return code, out.getvalue()

    def test_a_desktop_frame_alone_names_the_missing_phone_frame(self):
        code, out = self.run_frames([frame("1:1", "Release plan / Desktop", 1440)], ["1:1"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["Frames: Release plan / Desktop (1:1, 1440 wide).",
                                            "No phone frame: the phone layout is not from the design."])

    def test_a_phone_frame_given_prints_no_missing_line(self):
        code, out = self.run_frames([frame("1:1", "Desktop", 1440), frame("1:9", "Phone", 390)], ["1:1", "1:9"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["Frames: Desktop (1:1, 1440 wide); Phone (1:9, 390 wide)."])

    def test_a_tablet_frame_is_not_the_phone_frame(self):
        code, out = self.run_frames([frame("1:1", "Desktop", 1440), frame("1:5", "Tablet", 768)], ["1:1", "1:5"])
        self.assertIn("No phone frame: the phone layout is not from the design.", out)

    def test_a_frame_it_cannot_read_says_the_widths_are_unknown(self):
        def no_token(path):
            raise SystemExit("could not run: set FIGMA_TOKEN to a Figma personal access token")
        code, out = self.run_frames([], ["1:1"], figma_get=no_token)
        self.assertEqual(code, 2)
        self.assertEqual(out.strip(), "Frames: 1:1, widths unknown: could not run: set FIGMA_TOKEN to a Figma "
                                      "personal access token")


class PathsTest(unittest.TestCase):
    def test_frames_are_read_with_their_paths_and_a_cache_without_them_is_not_used(self):
        check = load()
        asked = []

        def figma_get(path):
            asked.append(path)
            return {"nodes": {"1:1": {"document": frame("1:1", "Desktop", 1440)}}}
        with tempfile.TemporaryDirectory() as cache:
            # what the check cached before it read paths
            Path(cache, "KEY-1-1.json").write_text(json.dumps(frame("1:1", "Old", 1440)), encoding="utf-8")
            with mock.patch.object(check, "figma_get", figma_get):
                got = check.fetch_frames("KEY", ["1:1"], cache)
                again = check.fetch_frames("KEY", ["1:1"], cache)
            self.assertEqual(got["1:1"]["name"], "Desktop")
            self.assertEqual(again["1:1"]["name"], "Desktop")
            self.assertEqual(len(asked), 1)  # the second read came from the cache it wrote
            self.assertIn("geometry=paths", asked[0])
            self.assertTrue(Path(check.cache_file(cache, "KEY", "1:1")).exists())


class NoBrowserTest(unittest.TestCase):
    def test_without_playwright_the_check_says_frames_still_work(self):
        check = load()

        def no_playwright(*args, **kwargs):
            raise ModuleNotFoundError("No module named 'playwright'")
        for args in (["--selftest"], ["page.html", "--file", "KEY", "--frame", "1:1"]):
            out = io.StringIO()
            with redirect_stdout(out), mock.patch.object(check, "check", no_playwright), \
                    mock.patch.object(check, "fetch_frames", lambda *a: {}):
                code = check.main(args)
            self.assertEqual(code, 2, args)
            self.assertIn("--frames needs no browser and still lists the frames.", out.getvalue(), args)


if __name__ == "__main__":
    unittest.main()
