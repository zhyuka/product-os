"""product-os design: the baseline a REST read fills, drift against it, and the list of
states a design draws.

The payloads are synthetic, in the shape tests/design_payload.py describes.
"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from product_os import design
from product_os.cli import main

import design_payload
from design_payload import STATES, payload


def files_in(folder):
    return sorted(p.relative_to(folder).as_posix() for p in Path(folder).rglob("*") if p.is_file())


class BaselineTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "design"

    def test_a_frame_is_written_with_its_sets_and_listed(self):
        entry = design.save_frame(self.folder, payload(), taken="2026-10-24T00:00:00+00:00")
        self.assertEqual(files_in(self.folder), [
            "frames/1-2/links.json", "frames/1-2/node.json", "index.json",
            "sets/10-0/10-1.json", "sets/10-0/10-2.json", "sets/10-0/10-3.json",
            "sets/10-0/10-4.json", "sets/10-0/10-5.json", "sets/10-0/set.json",
            "sets/11-0/11-1.json", "sets/11-0/11-2.json", "sets/11-0/set.json"])
        index = json.loads((self.folder / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["frames"], {"1:2": entry})
        self.assertEqual((entry["name"], entry["width"], entry["height"], entry["sets"]),
                         ("Home / Desktop", 1440, 900, ["10:0", "11:0"]))
        self.assertEqual(sorted(index["sets"]), ["10:0", "11:0"])

    def test_a_frame_moved_on_the_canvas_keeps_its_hash(self):
        here = design.save_frame(self.folder, payload())
        moved = design.save_frame(self.folder, payload(x=-3210.7, y=88.3))
        self.assertEqual(here["sha256"], moved["sha256"])

    def test_whole_numbers_hash_alike_however_they_were_written(self):
        # One tool saves 1440 where another saves 1440.0.
        written = payload()
        floats = json.loads(json.dumps(written).replace('"width": 1440', '"width": 1440.0'))
        self.assertNotEqual(json.dumps(written), json.dumps(floats))
        self.assertEqual(design.save_frame(self.folder, written)["sha256"],
                         design.save_frame(self.folder, floats)["sha256"])

    def test_a_change_to_the_design_changes_the_hash_it_belongs_to(self):
        first = design.save_frame(self.folder, payload())
        sets = json.loads((self.folder / "index.json").read_text(encoding="utf-8"))["sets"]
        recoloured = payload()
        recoloured["frame"]["node"]["document"]["children"][1]["fills"][0]["color"]["g"] = 0.4
        self.assertNotEqual(design.save_frame(self.folder, recoloured)["sha256"], first["sha256"])
        relinked = payload()
        link = relinked["frame"]["node"]["document"]["children"][2]
        link["interactions"][0]["actions"][0]["url"] = "https://example.com/help"
        self.assertNotEqual(design.save_frame(self.folder, relinked)["sha256"], first["sha256"])
        hover = payload()
        hover["sets"]["10:0"]["variants"][1]["node"]["document"]["fills"][0]["color"]["b"] = 0.5
        again = design.save_frame(self.folder, hover)
        index = json.loads((self.folder / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(again["sha256"], first["sha256"], "the frame itself didn't change")
        self.assertNotEqual(index["sets"]["10:0"]["sha256"], sets["10:0"]["sha256"])
        self.assertEqual(index["sets"]["11:0"]["sha256"], sets["11:0"]["sha256"])

    def test_a_frame_sent_without_its_sets_keeps_the_ones_already_saved(self):
        design.save_frame(self.folder, payload())
        alone = payload()
        alone["sets"] = {}
        design.save_frame(self.folder, alone)
        self.assertEqual(len(design.plan_states(self.folder)), len(STATES))

    def test_a_bad_payload_writes_nothing(self):
        cases = {
            "a path for an id": lambda p: p["frame"].update(id="../../escape"),
            "a set id that is a path": lambda p: p["sets"].update({"../x": p["sets"]["10:0"]}),
            "a variant id that is a path": lambda p: p["sets"]["10:0"]["variants"][0].update(id="a/b"),
            "an instance's set": lambda p: p["frame"]["instances"][0].update(set="..\\x"),
            "no node tree": lambda p: p["frame"].update(node={"components": {}}),
            "a reaction with no trigger": lambda p: p["frame"]["reactions"][0].update(trigger=None),
            "values that aren't strings": lambda p: p["frame"]["instances"][0].update(values={"a": 1}),
            "no frame": lambda p: p.pop("frame"),
        }
        for name, spoil in cases.items():
            with self.subTest(name):
                bad = payload()
                spoil(bad)
                with self.assertRaises(design.BaselineError):
                    design.save_frame(self.folder, bad)
                self.assertFalse(self.folder.exists())


def rest_answers(sent):
    """The REST API's answers for the payload's frame and for its component sets: the same
    design, read the other way. Instances carry componentProperties, reactions are the nodes'
    interactions, and a hidden layer with a reaction is added, which both ways leave out."""
    frame = sent["frame"]["node"]
    tree = frame["document"]
    for instance in sent["frame"]["instances"]:
        found = next(n for n in tree["children"] if n["id"] == instance["node"])
        found["componentProperties"] = {k: {"type": "VARIANT", "value": v}
                                        for k, v in instance["values"].items()}
    tree["children"].append(design_payload.node(
        "1:9", "FRAME", "Old banner", design_payload.box(0, 0, 10, 10), visible=False,
        interactions=[{"trigger": {"type": "ON_CLICK"}, "actions": [{"type": "BACK"}]}]))
    frame["components"] = {i["component"]: {"componentSetId": i["set"]}
                           for i in sent["frame"]["instances"]}
    sets = {}
    for set_id, entry in sent["sets"].items():
        children = []
        for variant in entry["variants"]:
            child = variant["node"]["document"]
            for reaction in variant["reactions"]:
                where = child if reaction["node"] == child["id"] else child["children"][0]
                where["interactions"] = [{"trigger": reaction["trigger"], "actions": reaction["actions"]}]
            children.append(child)
        sets[set_id] = {"document": {
            "id": set_id, "type": "COMPONENT_SET", "name": entry["name"], "children": children,
            "componentPropertyDefinitions": {k: {"type": "VARIANT", "variantOptions": v}
                                             for k, v in entry["properties"].items()}}}
    return {"name": "Example shop", "nodes": {"1:2": frame}}, {"nodes": sets}


class RestTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_a_rest_read_gives_the_states_and_hash_of_the_same_payload(self):
        nodes, sets = rest_answers(payload())
        sent = payload()  # the same tree as the REST answer, with its links listed by hand
        sent["frame"]["node"] = json.loads(json.dumps(nodes["nodes"]["1:2"]))
        by_hand = design.save_frame(self.root / "by-hand", sent)
        (read,) = design.from_rest(nodes, sets)
        self.assertEqual(design.save_frame(self.root / "rest", read)["sha256"], by_hand["sha256"])
        for folder in ("by-hand", "rest"):
            plan = [(s.node, s.do, s.keys, s.expect.get("kind"), s.expect.get("target"), s.source)
                    for s in design.plan_states(self.root / folder)]
            self.assertEqual(plan, STATES, folder)

    def test_hidden_layers_are_left_out(self):
        nodes, sets = rest_answers(payload())
        (read,) = design.from_rest(nodes, sets)
        self.assertNotIn("1:9", [r["node"] for r in read["frame"]["reactions"]])

    def test_without_the_sets_only_what_the_instances_show_is_known(self):
        nodes, _ = rest_answers(payload())
        (read,) = design.from_rest(nodes)
        design.save_frame(self.root / "rest", read)
        missing = [s.node for s in design.plan_states(self.root / "rest") if "isn't in" in s.why_not]
        self.assertEqual(missing, ["1:5", "1:7", "1:8"])

    def test_drift_says_which_frames_moved(self):
        nodes, _ = rest_answers(payload())
        design.save_frame(self.root / "snap", design.from_rest(nodes)[0])
        self.assertEqual(design.drift(self.root / "snap", nodes), [("1:2", "Home / Desktop", "unchanged")])
        nodes["nodes"]["1:2"]["document"]["children"][0]["characters"] = "Store"
        nodes["nodes"]["9:9"] = {"document": {"id": "9:9", "name": "Pricing"}}
        self.assertEqual(design.drift(self.root / "snap", nodes),
                         [("1:2", "Home / Desktop", "moved"), ("9:9", "Pricing", "not in the baseline")])

    def test_the_files_last_edit_says_whether_to_read_the_frames_again(self):
        snap = self.root / "snap"
        nodes, _ = rest_answers(payload())
        design.save_frame(snap, design.from_rest(nodes)[0])
        meta = {"file": {"name": "Example shop", "version": "101", "last_touched_at": "2026-10-24T10:00:00Z"}}
        self.assertEqual(design.drift(snap, meta=meta)[0][2], "edited since no recorded edit",
                         "nothing recorded yet, so the frames have to be read")
        self.assertEqual(design.drift(snap, nodes, meta)[0][2], "unchanged")
        self.assertEqual(design.drift(snap, meta=meta), [("file", "", "unchanged")], "now recorded")
        later = {"file": {**meta["file"], "version": "102", "last_touched_at": "2026-10-24T11:00:00Z"}}
        self.assertEqual(design.drift(snap, meta=later)[0][2], "edited since 2026-10-24T10:00:00Z")
        nodes["nodes"]["1:2"]["document"]["children"][0]["characters"] = "Store"
        design.drift(snap, nodes, later)
        self.assertEqual(design.drift(snap, meta=later)[0][2], "edited since 2026-10-24T10:00:00Z",
                         "a frame moved, so the newer edit isn't recorded as matched")
        with self.assertRaises(design.BaselineError):
            design.drift(snap, meta={"file": {"name": "x"}})

    def test_the_commands_import_and_check_drift(self):
        nodes, sets = rest_answers(payload())
        (self.root / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
        (self.root / "sets.json").write_text(json.dumps(sets), encoding="utf-8")
        snap = str(self.root / "snap")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["design", "import", str(self.root / "nodes.json"), "--sets",
                                   str(self.root / "sets.json"), "--baseline", snap]), 0)
            self.assertEqual(main(["design", "drift", str(self.root / "nodes.json"), "--baseline", snap]), 0)
        nodes["nodes"]["1:2"]["document"]["children"][0]["characters"] = "Store"
        (self.root / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["design", "drift", str(self.root / "nodes.json"), "--baseline", snap]), 1)


class StatesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "design"
        design.save_frame(self.folder, payload())

    def plan(self):
        return [(s.node, s.do, s.keys, s.expect.get("kind"), s.expect.get("target"), s.source)
                for s in design.plan_states(self.folder)]

    def test_every_state_the_design_draws_is_listed_once(self):
        self.assertEqual(self.plan(), STATES)

    def test_states_say_why_no_input_reaches_them(self):
        why = {s.state: s.why_not for s in design.plan_states(self.folder) if s.do == "none"}
        self.assertEqual(why, {
            "State=Disabled": "set by the build's data, not by an input",
            "shown as State=Disabled": "placed in a state other than the default, so its other "
                                       "states aren't listed"})

    def test_a_variant_the_design_doesnt_draw_is_not_listed(self):
        large = payload()
        large["frame"]["instances"][0]["values"]["Size"] = "Large"
        large["frame"]["instances"][0]["component"] = "10:5"
        design.save_frame(self.folder, large)
        states = [s for s in design.plan_states(self.folder) if s.node == "1:5"]
        self.assertEqual(states, [], "10:5 has no reactions and no Hover, Focus or Disabled at Large")

    def test_a_missing_component_set_is_listed_not_skipped(self):
        alone = payload()
        alone["sets"] = {}
        folder = self.folder.parent / "alone"
        design.save_frame(folder, alone)
        missing = [s for s in design.plan_states(folder) if s.why_not.endswith("isn't in the baseline")]
        self.assertEqual([s.node for s in missing], ["1:5", "1:7", "1:8"])

    def test_which_properties_hold_states(self):
        self.assertEqual(design._state_properties({
            "State": ["Default", "Hover"], "accordion state": ["NA", "open", "closed"],
            "Hover": ["False", "True"], "Type": ["Utility", "Error", "Image"],
            "Size": ["SM", "MD"], "type": ["primary", "inactive"]}),
            {"State": "options", "accordion state": "options", "Hover": "switch"})

    def test_a_sublayer_id_has_one_i_however_deep(self):
        self.assertEqual(design._sublayer("1:5", "10:9"), "I1:5;10:9")
        self.assertEqual(design._sublayer("I1:5;7:3", "I7:4;8:1"), "I1:5;7:3;7:4;8:1")

    def test_each_state_carries_its_text_to_be_found_by(self):
        texts = {s.node: (s.texts, s.text_ordinal) for s in design.plan_states(self.folder)}
        self.assertEqual(texts["1:5"], (["Get started"], 0))
        self.assertEqual(texts["1:6"], (["Docs"], 0))
        self.assertEqual(texts["1:2"], (["Shop", "Get started"], 0))

    def test_key_codes_become_key_names(self):
        self.assertEqual(design.keys_for([75]), "k")
        self.assertEqual(design.keys_for([16, 9]), "Shift+Tab")
        self.assertEqual(design.keys_for([27]), "Escape")
        self.assertEqual(design.keys_for([17, 18]), "", "two modifiers and no key")
        self.assertEqual(design.keys_for([250]), "", "no name for this code")
        unnamed = payload()
        unnamed["frame"]["reactions"][0]["trigger"]["keyCodes"] = [250]
        design.save_frame(self.folder, unnamed)
        first = design.plan_states(self.folder)[0]
        self.assertEqual((first.do, first.why_not), ("none", "key codes [250] have no name here"))

    def test_reactions_with_no_input_here_are_listed_as_not_exercised(self):
        dragged = payload()
        dragged["frame"]["reactions"][1]["trigger"] = {"type": "ON_DRAG"}
        design.save_frame(self.folder, dragged)
        second = design.plan_states(self.folder)[1]
        self.assertEqual((second.do, second.why_not), ("none", "a ON_DRAG reaction isn't exercised"))

    def test_the_command_lists_them(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["design", "states", "--baseline", str(self.folder)]), 0)
        self.assertIn("8 states: 6 reached by an input, 2 not.", out.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["design", "states", "--baseline", str(self.folder), "--json"]), 0)
        self.assertEqual(len(json.loads(out.getvalue())), 8)

    def test_no_baseline_is_unusable_input(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", err):
            self.assertEqual(main(["design", "states", "--baseline", str(self.folder.parent / "x")]), 2)
        self.assertIn("no baseline here", err.getvalue())
        with self.assertRaises(design.BaselineError):
            design.plan_states(self.folder, ["9:9"])


if __name__ == "__main__":
    unittest.main()
