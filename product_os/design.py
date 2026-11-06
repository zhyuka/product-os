"""product-os design: record a Figma design as a baseline, and list the states a build has
to reach.

A baseline is a folder, design/ by default, that `product-os design import` fills from saved
REST API answers: GET /v1/files/:key/nodes for the frames, and the same call for the component
sets they use. It writes:

    design/index.json                      the frames and component sets, each with a SHA-256
    design/frames/<id>/node.json           the frame's node tree, in the REST API's JSON format
    design/frames/<id>/links.json          its prototype reactions and component instances
    design/sets/<id>/set.json              a component set the frames use: its properties, and
                                           each variant's values and reactions
    design/sets/<id>/<variant>.json        each variant's node tree

Hidden layers are left out.

A node id becomes a folder name with : as - and ; as _, so 1:2 is frames/1-2.

The baseline records what was signed off, not a stand-in for live Figma. Builders, checks and
CI read it from the repo, and check it against live Figma before they rely on it:
`design drift --meta` compares the file's last edit, from one call to
GET /v1/files/:key/meta, with the edit the baseline is known to match, and `design drift` with
a fresh read of the frames says which moved. Read /meta first, then the frames, so the edit
recorded is never newer than the frames read. Nothing else calls Figma while a build runs.

A frame's hash covers its node tree, prototype reactions included, with positions taken from the
frame's corner, so moving the frame on the canvas doesn't change it. A set's hash covers its
variants the same way. Either changes only when that part of the design does, so an approval
recorded against the hashes holds until the design moves. Everything else in the tree counts, a
renamed layer included.

`product-os design states` lists every state the design draws for the build to reach: each
prototype reaction (hover, press, click, a key, a timeout) and each drawn variant of a used
component whose value names a state, such as State=Hover or Open=True. A state no input reaches,
such as Disabled or Error, is listed as not exercised. `product-os design exercise URL`
(exercise.py) drives the build into each one.
"""
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FOLDER = "design"
NODE_ID = re.compile(r"I?\d+:\d+(?:;\d+:\d+)*\Z")


class BaselineError(Exception):
    """A payload or a baseline that can't be used. The message says why."""


# Writing a baseline -------------------------------------------------------------

def folder_name(node_id):
    """A Figma node id as a folder name. Anything that isn't a node id is refused, so a
    payload can't name a path outside the baseline."""
    if not isinstance(node_id, str) or not NODE_ID.match(node_id):
        raise BaselineError(f"{node_id!r} is not a Figma node id")
    return node_id.replace(":", "-").replace(";", "_")


def node_tree(export, what):
    """The node tree in an entry of a REST /nodes answer, which holds it under document."""
    if isinstance(export, dict) and isinstance(export.get("document"), dict):
        export = export["document"]
    if not isinstance(export, dict) or not isinstance(export.get("id"), str):
        raise BaselineError(f"{what}: the node export has no node tree")
    return export


def _offset(value, origin):
    """value - origin to a thousandth of a pixel, as an int when it is whole, so 124 and 124.0
    hash alike."""
    value = round(value - origin, 3)
    return int(value) if value == int(value) else value


def _from_corner(value, x, y):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if (key in ("absoluteBoundingBox", "absoluteRenderBounds") and isinstance(item, dict)
                    and _number(item.get("x")) is not None and _number(item.get("y")) is not None):
                item = {**item, "x": _offset(item["x"], x), "y": _offset(item["y"], y)}
            out[key] = _from_corner(item, x, y)
        return out
    if isinstance(value, list):
        return [_from_corner(item, x, y) for item in value]
    return value


def from_corner(tree):
    """The tree with every absolute position measured from the tree's own top-left corner."""
    box = tree.get("absoluteBoundingBox") or {}
    return _from_corner(tree, _number(box.get("x")) or 0, _number(box.get("y")) or 0)


def _numbers(value):
    """Every number to a thousandth, as an int when it is whole. One tool saves 1440 where
    another saves 1440.0, and two reads can differ in the last digits of a float, so a tree
    saved either way hashes the same."""
    if isinstance(value, dict):
        return {key: _numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_numbers(item) for item in value]
    if isinstance(value, float) and math.isfinite(value):
        value = round(value, 3)
        return int(value) if value == int(value) else value
    return value


def sha256(value):
    """SHA-256 of a JSON value with its keys sorted and its numbers rounded, so the same design
    gives the same hash however it was read."""
    text = json.dumps(_numbers(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tree_sha256(tree):
    """A frame's hash: its node tree, prototype reactions (interactions) included, measured
    from its corner."""
    return sha256(from_corner(tree))


def write_atomic(path, data):
    """Write bytes to a temp file beside path, then move it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def write_json(path, value):
    write_atomic(path, (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _strings(value, what):
    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
        raise BaselineError(f"{what}: values must be an object of strings")
    return dict(value)


def _reactions(items, what):
    if items is None:
        return []
    if not isinstance(items, list):
        raise BaselineError(f"{what}: reactions must be a list")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise BaselineError(f"{what}: a reaction must be an object")
        folder_name(item.get("node"))
        trigger = item.get("trigger")
        actions = item.get("actions", [item["action"]] if item.get("action") else [])
        if not isinstance(trigger, dict) or not isinstance(trigger.get("type"), str):
            raise BaselineError(f"{what}: reaction on {item['node']} has no trigger type")
        if not isinstance(actions, list) or not all(isinstance(a, dict) for a in actions):
            raise BaselineError(f"{what}: reaction on {item['node']} has unreadable actions")
        out.append({"node": item["node"], "name": str(item.get("name") or ""),
                    "trigger": trigger, "actions": actions})
    return out


def _instances(items, what):
    if items is None:
        return []
    if not isinstance(items, list):
        raise BaselineError(f"{what}: instances must be a list")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise BaselineError(f"{what}: an instance must be an object")
        folder_name(item.get("node"))
        for key in ("component", "set"):
            if item.get(key) is not None:
                folder_name(item[key])
        out.append({"node": item["node"], "name": str(item.get("name") or ""),
                    "component": item.get("component"), "set": item.get("set"),
                    "values": _strings(item.get("values") or {}, f"{what}: instance {item['node']}")})
    return out


def _component_set(set_id, entry):
    """(set.json's content, {file name: bytes}, hash) for one component set."""
    what = f"component set {set_id}"
    if not isinstance(entry, dict) or not isinstance(entry.get("variants"), list):
        raise BaselineError(f"{what}: no variants list")
    properties = entry.get("properties") or {}
    if not isinstance(properties, dict) or not all(
            isinstance(v, list) and all(isinstance(o, str) for o in v) for v in properties.values()):
        raise BaselineError(f"{what}: properties must map each name to a list of options")
    content = {"name": str(entry.get("name") or ""), "properties": properties, "variants": []}
    files, trees = {}, {}
    for variant in entry["variants"]:
        if not isinstance(variant, dict):
            raise BaselineError(f"{what}: a variant must be an object")
        name = folder_name(variant.get("id"))
        where = f"variant {variant['id']}"
        if variant.get("node") is not None:
            trees[variant["id"]] = from_corner(node_tree(variant["node"], where))
            files[name + ".json"] = (json.dumps(variant["node"], indent=2, ensure_ascii=False)
                                     + "\n").encode("utf-8")
        content["variants"].append({
            "id": variant["id"], "name": str(variant.get("name") or ""),
            "values": _strings(variant.get("values") or {}, where),
            "reactions": _reactions(variant.get("reactions"), where)})
    return content, files, sha256({"set": content, "trees": trees})


def read_index(folder):
    path = Path(folder) / "index.json"
    if not path.is_file():
        return {"format": 1, "frames": {}, "sets": {}}
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise BaselineError(f"{path} could not be read") from None
    if not isinstance(index, dict) or not isinstance(index.get("frames"), dict):
        raise BaselineError(f"{path} has no frames object")
    index.setdefault("sets", {})
    return index


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_frame(folder, payload, taken=None):
    """Write one frame's payload, from from_rest, with the component sets beside it, and list
    them in index.json. Everything is checked before anything is written. Returns the frame's
    index entry."""
    folder = Path(folder)
    frame = payload.get("frame") if isinstance(payload, dict) else None
    if not isinstance(frame, dict):
        raise BaselineError("the payload has no frame")
    frame_id = frame.get("id")
    where = folder_name(frame_id)
    what = f"frame {frame_id}"
    export = frame.get("node")
    tree = node_tree(export, what)
    links = {"reactions": _reactions(frame.get("reactions"), what),
             "instances": _instances(frame.get("instances"), what)}
    sent = payload.get("sets") or {}
    if not isinstance(sent, dict):
        raise BaselineError("sets must be an object")
    sets = {set_id: (folder_name(set_id), *_component_set(set_id, entry))
            for set_id, entry in sent.items()}
    file = payload.get("file") if isinstance(payload.get("file"), dict) else {}
    box = tree.get("absoluteBoundingBox") or {}
    taken = taken or now()
    entry = {"name": str(frame.get("name") or tree.get("name") or ""),
             "file": str(file.get("name") or ""), "page": str(file.get("page") or ""),
             "file_key": file["key"] if isinstance(file.get("key"), str) else None,
             "width": _number(box.get("width")), "height": _number(box.get("height")),
             "sha256": tree_sha256(tree), "taken": taken,
             "sets": sorted({i["set"] for i in links["instances"] if i["set"]})}
    index = read_index(folder)
    for set_id, (name, content, files, digest) in sets.items():
        for file_name, data in files.items():
            write_atomic(folder / "sets" / name / file_name, data)
        write_json(folder / "sets" / name / "set.json", content)
        index["sets"][set_id] = {"name": content["name"], "sha256": digest, "taken": taken}
    base = folder / "frames" / where
    write_json(base / "node.json", export)
    write_json(base / "links.json", links)
    index["format"] = 1
    index["frames"][frame_id] = entry
    index["frames"] = dict(sorted(index["frames"].items()))
    index["sets"] = dict(sorted(index["sets"].items()))
    write_json(folder / "index.json", index)
    return entry


# Reading the REST API's JSON ---------------------------------------------------------

def _shown(node, reactions, instances, components):
    """Collect the prototype reactions and component instances under node, leaving out a
    hidden layer and everything inside it."""
    if node.get("visible") is False:
        return
    for interaction in node.get("interactions") or []:
        if isinstance(interaction, dict) and isinstance(interaction.get("trigger"), dict):
            reactions.append({"node": node["id"], "name": node.get("name", ""),
                              "trigger": interaction["trigger"],
                              "actions": interaction.get("actions") or []})
    if node.get("type") == "INSTANCE":
        component = node.get("componentId")
        properties = node.get("componentProperties") or {}
        instances.append({
            "node": node["id"], "name": node.get("name", ""), "component": component,
            "set": (components.get(component) or {}).get("componentSetId"),
            "values": {k: str(v.get("value")) for k, v in properties.items()
                       if isinstance(v, dict) and v.get("type") == "VARIANT"}})
    for child in node.get("children") or []:
        _shown(child, reactions, instances, components)


def _values_from_name(name):
    """A variant's values from its name, which Figma writes as "A=x, B=y"."""
    out = {}
    for part in str(name).split(","):
        key, sep, value = part.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def _rest_set(tree):
    properties = {k: list(v.get("variantOptions") or [])
                  for k, v in (tree.get("componentPropertyDefinitions") or {}).items()
                  if isinstance(v, dict) and v.get("type") == "VARIANT"}
    variants = []
    for child in tree.get("children") or []:
        if child.get("type") != "COMPONENT":
            continue
        reactions = []
        _shown(child, reactions, [], {})
        variants.append({"id": child["id"], "name": child.get("name", ""),
                         "values": _values_from_name(child.get("name", "")),
                         "reactions": reactions, "node": {"document": child}})
    return {"name": tree.get("name", ""), "properties": properties, "variants": variants}


def from_rest(response, sets=None, file_key=None):
    """Payloads for save_frame, one per frame, from a REST API response to
    GET /v1/files/:key/nodes?ids=<frames>. sets is a second such response for the ids of the
    component sets the frames use (the componentSets in the first); without it, the variants
    the frames' instances don't show aren't known."""
    nodes = response.get("nodes") if isinstance(response, dict) else None
    if not isinstance(nodes, dict):
        raise BaselineError("not a GET /v1/files/:key/nodes response: it has no nodes object")
    known = {}
    for set_id, entry in ((sets or {}).get("nodes") or {}).items():
        tree = (entry or {}).get("document") or {}
        if tree.get("type") == "COMPONENT_SET":
            known[set_id] = _rest_set(tree)
    payloads = []
    for node_id, entry in nodes.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("document"), dict):
            raise BaselineError(f"node {node_id} isn't in the file, or can't be read")
        tree = entry["document"]
        reactions, instances = [], []
        _shown(tree, reactions, instances, entry.get("components") or {})
        used = {i["set"] for i in instances if i["set"]}
        payloads.append({
            "file": {"name": response.get("name", ""), "key": file_key, "page": ""},
            "frame": {"id": tree["id"], "name": tree.get("name", ""), "node": entry,
                      "reactions": reactions, "instances": instances},
            "sets": {s: known[s] for s in sorted(used) if s in known}})
    return payloads


def file_state(meta):
    """{version, last_touched_at} from a REST answer to GET /v1/files/:key/meta: the file's
    last edit, which changes whenever anything in the file does."""
    entry = meta.get("file", meta) if isinstance(meta, dict) else None
    state = {k: entry.get(k) for k in ("version", "last_touched_at")} if isinstance(entry, dict) else {}
    if not state or not all(isinstance(v, str) and v for v in state.values()):
        raise BaselineError("not a GET /v1/files/:key/meta answer: it has no version and "
                            "last_touched_at")
    return state


def record_file_state(folder, meta):
    """Note in index.json the file's last edit that the baseline is known to match."""
    index = read_index(folder)
    index["file_state"] = {**file_state(meta), "checked": now()}
    write_json(Path(folder) / "index.json", index)


def drift(folder, response=None, meta=None):
    """[(frame id, name, "unchanged", "moved" or "not in the baseline")] for each frame in a
    fresh REST read of its nodes, against the baseline's hashes. With meta alone, one row for
    the whole file: "unchanged" when its last edit is the one the baseline was last known to
    match, else "edited since", which needs a read of the nodes to say which frames moved.
    When every frame is unchanged and meta is given, the baseline records that last edit."""
    index = read_index(folder)
    if response is None:
        state, known = file_state(meta), index.get("file_state") or {}
        same = all(known.get(k) == v for k, v in state.items())
        when = known.get("last_touched_at") or "no recorded edit"
        return [("file", "", "unchanged" if same else f"edited since {when}")]
    out = []
    for node_id, entry in (response.get("nodes") or {}).items():
        tree = node_tree(entry, f"node {node_id}")
        saved = index["frames"].get(tree["id"])
        if saved is None:
            out.append((tree["id"], tree.get("name", ""), "not in the baseline"))
        else:
            same = saved["sha256"] == tree_sha256(tree)
            out.append((tree["id"], saved["name"], "unchanged" if same else "moved"))
    covered = {row[0] for row in out if row[2] == "unchanged"}
    if meta is not None and index["frames"] and set(index["frames"]) <= covered:
        record_file_state(folder, meta)
    return out


# The states a design draws --------------------------------------------------------

BASE = {"default", "rest", "resting", "idle", "enabled", "normal", "off", "closed", "collapsed",
        "unselected", "unchecked", "inactive", "false", "no", "na", "n/a", "none"}
TRUE = {"true", "yes", "on"}
INPUTS = {"hover": "hover", "hovered": "hover", "focus": "focus", "focused": "focus",
          "focus visible": "focus", "keyboard focus": "focus", "pressed": "press", "press": "press",
          "active": "press", "open": "click", "opened": "click", "expanded": "click",
          "selected": "click", "checked": "click"}
DATA = {"disabled", "loading", "error"}  # states, but set by the build's data, not an input
STATE_NAMES = ("state", "status", "interaction")  # a property named like this holds states
TRIGGERS = {"ON_HOVER": "hover", "MOUSE_ENTER": "hover", "ON_PRESS": "press",
            "MOUSE_DOWN": "press", "ON_CLICK": "click", "MOUSE_UP": "click",
            "ON_KEY_DOWN": "key", "AFTER_TIMEOUT": "wait"}
MODIFIERS = {16: "Shift", 17: "Control", 18: "Alt", 91: "Meta", 93: "Meta"}
KEYS = {8: "Backspace", 9: "Tab", 13: "Enter", 27: "Escape", 32: "Space", 33: "PageUp",
        34: "PageDown", 35: "End", 36: "Home", 37: "ArrowLeft", 38: "ArrowUp", 39: "ArrowRight",
        40: "ArrowDown", 46: "Delete"}
NAVIGATION = {"NAVIGATE": "navigate", "OVERLAY": "overlay", "SWAP": "swap",
              "SCROLL_TO": "scroll", "CHANGE_TO": "variant"}


@dataclass
class State:
    """One state the design draws. do is the input that reaches it: hover, focus (by Tab),
    press, click, key, wait, or none when no input does (why_not says why). expect is what
    the design says happens: kind (variant, navigate, overlay, swap, scroll, url, back,
    close or change), target (a node id or a URL) and, for a variant, its values."""
    frame: str
    frame_name: str
    width: object
    node: str
    name: str
    state: str
    do: str
    keys: str = ""
    expect: dict = field(default_factory=dict)
    source: list = field(default_factory=list)
    why_not: str = ""
    component_set: object = None  # the set of the instance the state is on, when it is one
    set_name: str = ""
    ordinal: int = 0  # which instance of that set it is in the frame, counting from 0
    texts: list = field(default_factory=list)  # the node's first two texts, to find it by
    text_ordinal: int = 0  # which of the states' nodes with the same first text it is


def _word(text):
    return " ".join(str(text).lower().replace("_", " ").replace("-", " ").split())


def keys_for(codes):
    """Figma key codes, pressed together, as a Playwright key chord, or "" when one has no
    name here."""
    if not isinstance(codes, list) or not codes:
        return ""
    held, pressed = [], []
    for code in codes:
        if code in MODIFIERS:
            held.append(MODIFIERS[code])
        elif code in KEYS:
            pressed.append(KEYS[code])
        elif isinstance(code, int) and (48 <= code <= 57 or 65 <= code <= 90):
            pressed.append(chr(code).lower())
        else:
            return ""
    if len(pressed) != 1:
        return ""
    return "+".join(held + pressed)


def _expect(action, values):
    kind = action.get("type")
    if kind == "NODE":
        target = action.get("destinationId")
        expect = {"kind": NAVIGATION.get(action.get("navigation"), "navigate"), "target": target}
        if expect["kind"] == "variant":
            expect["values"] = values.get(target, {})
        return expect
    if kind == "URL":
        return {"kind": "url", "target": action.get("url")}
    if kind in ("BACK", "CLOSE"):
        return {"kind": kind.lower(), "target": None}
    return {"kind": "change", "target": None}


def _describe(expect):
    kind, target = expect["kind"], expect.get("target")
    if kind == "variant":
        values = expect.get("values") or {}
        return ", ".join(f"{k}={v}" for k, v in values.items()) or f"variant {target}"
    if kind in ("back", "close", "change"):
        return kind
    return f"{kind} {target}"


def _sublayer(instance, node):
    """The id a component's sublayer has inside an instance of it: I<instance>;<sublayer>, with
    one I at the front however deep either is nested."""
    return f"I{instance.lstrip('I')};{node.lstrip('I')}"


def _from_reaction(base, node, name, reaction, values):
    trigger = reaction["trigger"]
    kind = trigger.get("type")
    do = TRIGGERS.get(kind, "none")
    keys = keys_for(trigger.get("keyCodes")) if do == "key" else ""
    why_not = ""
    if do == "none":
        why_not = f"a {kind} reaction isn't exercised"
    elif do == "key" and not keys:
        do, why_not = "none", f"key codes {trigger.get('keyCodes')} have no name here"
    actions = reaction["actions"] or [{"type": "NONE"}]
    for action in actions:
        expect = _expect(action, values)
        label = f"{(keys or kind.lower().replace('_', ' '))}: {_describe(expect)}"
        yield State(**base, node=node, name=name, state=label, do=do, keys=keys, expect=expect,
                    source=["reaction"], why_not=why_not)


def _state_properties(properties):
    """{property: kind} for the properties whose options are states: "options" when an option
    names an input's state, or the property is named like State; "switch" when the property's
    own name is an input's state and its options are true and false. An option such as Error
    alone doesn't make one: an icon set can have an Error icon."""
    out = {}
    for prop, options in properties.items():
        words = {_word(o) for o in options}
        if words & set(INPUTS) or any(name in _word(prop) for name in STATE_NAMES):
            out[prop] = "options"
        elif _word(prop) in INPUTS and words <= BASE | TRUE:
            out[prop] = "switch"
    return out


def _from_variants(base, instance, component_set):
    """States for the instance's other drawn variants that differ in one state property."""
    current = instance["values"]
    drawn = {tuple(sorted(v["values"].items())): v for v in component_set["variants"]}
    for prop, kind in _state_properties(component_set["properties"]).items():
        value = current.get(prop)
        if value is None:
            continue
        if _word(value) not in BASE:
            yield State(**base, node=instance["node"], name=instance["name"],
                        state=f"shown as {prop}={value}", do="none", source=["variant"],
                        why_not="placed in a state other than the default, so its other "
                                "states aren't listed")
            continue
        for option in component_set["properties"][prop]:
            if option == value or _word(option) in BASE:
                continue
            variant = drawn.get(tuple(sorted({**current, prop: option}.items())))
            if variant is None:
                continue  # the design doesn't draw this combination
            word = _word(prop) if kind == "switch" else _word(option)
            do = INPUTS.get(word, "none")
            why_not = "" if do != "none" else (
                "set by the build's data, not by an input" if word in DATA
                else "no input is known to reach it")
            yield State(**base, node=instance["node"], name=instance["name"],
                        state=f"{prop}={option}", do=do,
                        expect={"kind": "variant", "target": variant["id"],
                                "values": variant["values"]},
                        source=["variant"], why_not=why_not)


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise BaselineError(f"{path} could not be read") from None


def plan_states(folder=FOLDER, frames=None):
    """Every state the baseline's frames draw, frame by frame. Raises BaselineError."""
    folder = Path(folder)
    if not (folder / "index.json").is_file():
        raise BaselineError(f"{folder / 'index.json'}: no baseline here. Make one with "
                            "product-os design import")
    index = read_index(folder)
    wanted = list(index["frames"]) if not frames else frames
    missing = [f for f in wanted if f not in index["frames"]]
    if missing:
        raise BaselineError(f"no frame {', '.join(missing)} in {folder / 'index.json'}")
    sets = {}
    for set_id in index["sets"]:
        path = folder / "sets" / folder_name(set_id) / "set.json"
        if path.is_file():
            sets[set_id] = _read_json(path)
    values = {v["id"]: v["values"] for s in sets.values() for v in s["variants"]}
    states = []
    for frame_id in wanted:
        entry = index["frames"][frame_id]
        base = {"frame": frame_id, "frame_name": entry.get("name", ""), "width": entry.get("width")}
        links = _read_json(folder / "frames" / folder_name(frame_id) / "links.json")
        found = []
        for reaction in links.get("reactions", []):
            found += _from_reaction(base, reaction["node"], reaction["name"], reaction, values)
        for instance in links.get("instances", []):
            component_set = sets.get(instance.get("set"))
            if instance.get("set") and component_set is None:
                found.append(State(**base, node=instance["node"], name=instance["name"],
                                   state="its component's states", do="none", source=["variant"],
                                   why_not=f"component set {instance['set']} isn't in the "
                                           "baseline"))
                continue
            if component_set is None:
                continue
            for variant in component_set["variants"]:
                if variant["id"] != instance.get("component"):
                    continue
                for reaction in variant["reactions"]:
                    node = (instance["node"] if reaction["node"] == variant["id"]
                            else _sublayer(instance["node"], reaction["node"]))
                    found += _from_reaction(base, node, instance["name"], reaction, values)
            found += _from_variants(base, instance, component_set)
        owners, counts = {}, {}
        for instance in links.get("instances", []):  # in the frame's layer order
            set_id = instance.get("set")
            if set_id:
                name = (sets.get(set_id) or {}).get("name", "")
                owners[instance["node"]] = (set_id, name, counts.get(set_id, 0))
                counts[set_id] = counts.get(set_id, 0) + 1
        for state in found:
            if state.node in owners:
                state.component_set, state.set_name, state.ordinal = owners[state.node]
        found = _merge(found)
        _add_texts(found, node_tree(_read_json(folder / "frames" / folder_name(frame_id)
                                               / "node.json"), f"frame {frame_id}"))
        states += found
    return states


def _plain_text(text):
    return " ".join(str(text).replace(chr(0x200B), "").split())  # zero-width spaces dropped


def _add_texts(states, tree):
    """Give each state its node's first two shown texts, and its place among the states'
    nodes that start with the same text, in layer order."""
    order, texts = {}, {}

    def walk(node):
        order[node["id"]] = len(order)
        found = []
        if node.get("type") == "TEXT" and _plain_text(node.get("characters", "")):
            found.append(_plain_text(node["characters"]))
        for child in node.get("children") or []:
            if child.get("visible") is not False:
                found += [t for t in walk(child) if t not in found]
        texts[node["id"]] = found[:2]
        return found[:2]
    walk(tree)
    seen = {}
    for node in sorted({s.node for s in states}, key=lambda n: order.get(n, len(order))):
        first = (texts.get(node) or [""])[0]
        seen.setdefault(first, []).append(node)
    for state in states:
        state.texts = texts.get(state.node, [])
        if state.texts:
            state.text_ordinal = seen[state.texts[0]].index(state.node)


def _merge(found):
    """One state per node, input and outcome; the sources of duplicates are combined."""
    out = {}
    for state in found:
        key = (state.node, state.do, state.keys, state.expect.get("kind"),
               state.expect.get("target"), state.state if state.do == "none" else "")
        if key in out:
            out[key].source = sorted(set(out[key].source) | set(state.source))
        else:
            out[key] = state
    return list(out.values())
