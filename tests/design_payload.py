"""A synthetic payload in the shape design.save_frame takes: one desktop frame of a made-up
shop page, with a Button component set, a Menu component set, a link and a key reaction.

    frame 1:2 "Home / Desktop", 1440 x 900; key k opens overlay 1:20
      1:5  Button, State=Default, Size=Medium; its variant hovers to State=Hover, and the
           variant's label 10:9 navigates to frame 3:1 on click
      1:6  Docs link: a click opens https://example.com/docs
      1:7  Menu, Open=False; a click changes it to Open=True
      1:8  Button, State=Disabled

The Button set draws Default, Hover, Focus and Disabled at Medium, and only Default at Large.
"""
import copy


def box(x, y, width, height):
    return {"x": x, "y": y, "width": width, "height": height}


def node(node_id, kind, name, bounds, **fields):
    return {"id": node_id, "type": kind, "name": name, "absoluteBoundingBox": bounds,
            "absoluteRenderBounds": dict(bounds), **fields}


def fill(r, g, b):
    return [{"type": "SOLID", "color": {"r": r, "g": g, "b": b, "a": 1}}]


def reaction(node_id, name, trigger, *actions):
    return {"node": node_id, "name": name, "trigger": trigger, "actions": list(actions)}


def go(navigation, destination):
    return {"type": "NODE", "destinationId": destination, "navigation": navigation}


def variant(variant_id, values, colour, reactions=()):
    name = ", ".join(f"{k}={v}" for k, v in values.items())
    left, right = variant_id.split(":")
    label = f"{left}:{int(right) + 8}"  # 10:1's label is 10:9
    tree = node(variant_id, "COMPONENT", name, box(0, 0, 160, 48), fills=fill(*colour),
                children=[node(label, "TEXT", "Label", box(24, 12, 112, 24), characters="Get started")])
    return {"id": variant_id, "name": name, "values": values, "reactions": list(reactions),
            "node": {"document": tree, "components": {}, "styles": {}}}


def payload(x=1000, y=500):
    """A fresh payload with the frame's top-left corner at (x, y) on the canvas."""
    key = reaction("1:2", "Home / Desktop", {"type": "ON_KEY_DOWN", "device": "KEYBOARD",
                                             "keyCodes": [75]}, go("OVERLAY", "1:20"))
    docs = reaction("1:6", "Docs link", {"type": "ON_CLICK"},
                    {"type": "URL", "url": "https://example.com/docs"})

    def text(node_id, words, left):
        return [node(node_id, "TEXT", "Label", box(x + left, y + 112, 80, 24), characters=words)]
    tree = node("1:2", "FRAME", "Home / Desktop", box(x, y, 1440, 900), fills=fill(1, 1, 1),
                interactions=[{k: key[k] for k in ("trigger", "actions")}], children=[
                    node("1:3", "TEXT", "Title", box(x + 100, y + 40, 600, 48), characters="Shop"),
                    node("1:5", "INSTANCE", "Button", box(x + 100, y + 100, 160, 48),
                         componentId="10:1", fills=fill(0, 0.33, 1),
                         children=text("I1:5;10:9", "Get started", 124)),
                    node("1:6", "FRAME", "Docs link", box(x + 300, y + 100, 80, 24),
                         interactions=[{k: docs[k] for k in ("trigger", "actions")}],
                         children=text("1:16", "Docs", 300)),
                    node("1:7", "INSTANCE", "Menu", box(x + 400, y + 100, 120, 48),
                         componentId="11:1", children=text("I1:7;11:9", "Menu", 412)),
                    node("1:8", "INSTANCE", "Button", box(x + 600, y + 100, 160, 48),
                         componentId="10:4", fills=fill(0.8, 0.8, 0.8),
                         children=text("I1:8;10:12", "Later", 624)),
                ])
    hover = reaction("10:1", "State=Default, Size=Medium", {"type": "ON_HOVER"},
                     go("CHANGE_TO", "10:2"))
    label = reaction("10:9", "Label", {"type": "ON_CLICK"}, go("NAVIGATE", "3:1"))
    medium = {"Size": "Medium"}
    buttons = {"name": "Button",
               "properties": {"State": ["Default", "Hover", "Focus", "Disabled"],
                              "Size": ["Medium", "Large"]},
               "variants": [variant("10:1", {"State": "Default", **medium}, (0, 0.33, 1), [hover, label]),
                            variant("10:2", {"State": "Hover", **medium}, (0, 0.2, 0.67)),
                            variant("10:3", {"State": "Focus", **medium}, (0, 0.33, 1)),
                            variant("10:4", {"State": "Disabled", **medium}, (0.8, 0.8, 0.8)),
                            variant("10:5", {"State": "Default", "Size": "Large"}, (0, 0.33, 1))]}
    menus = {"name": "Menu", "properties": {"Open": ["False", "True"]},
             "variants": [variant("11:1", {"Open": "False"}, (1, 1, 1),
                                  [reaction("11:1", "Open=False", {"type": "ON_CLICK"},
                                            go("CHANGE_TO", "11:2"))]),
                          variant("11:2", {"Open": "True"}, (0.95, 0.95, 0.95))]}
    return copy.deepcopy({
        "file": {"name": "Example shop", "key": None, "page": "Pages"},
        "frame": {
            "id": "1:2", "name": "Home / Desktop",
            "node": {"document": tree, "components": {}, "styles": {}, "schemaVersion": 0},
            "reactions": [key, docs],
            "instances": [
                {"node": "1:5", "name": "Button", "component": "10:1", "set": "10:0",
                 "values": {"State": "Default", "Size": "Medium"}},
                {"node": "1:7", "name": "Menu", "component": "11:1", "set": "11:0",
                 "values": {"Open": "False"}},
                {"node": "1:8", "name": "Button", "component": "10:4", "set": "10:0",
                 "values": {"State": "Disabled", "Size": "Medium"}},
            ],
        },
        "sets": {"10:0": buttons, "11:0": menus},
    })


# The states the payload draws, as (node, input, keys, outcome kind, target, source).
STATES = [
    ("1:2", "key", "k", "overlay", "1:20", ["reaction"]),
    ("1:6", "click", "", "url", "https://example.com/docs", ["reaction"]),
    ("1:5", "hover", "", "variant", "10:2", ["reaction", "variant"]),
    ("I1:5;10:9", "click", "", "navigate", "3:1", ["reaction"]),
    ("1:5", "focus", "", "variant", "10:3", ["variant"]),
    ("1:5", "none", "", "variant", "10:4", ["variant"]),
    ("1:7", "click", "", "variant", "11:2", ["reaction", "variant"]),
    ("1:8", "none", "", None, None, ["variant"]),
]
