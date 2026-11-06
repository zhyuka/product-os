"""Check a built page against its Figma frames. No AI inside.

For every visible text layer in each Figma frame, it checks the page at that frame's width:
the copy is there, the size, weight, line height, letter spacing and colour match, the text sits
where the design puts it, and it is smoothed the way Figma draws text. For every visible line
(a LINE layer) and every side of a box's stroke, it checks the rows the page draws it on and its
colour, and a line's run. For every box with a solid fill, it reads the fill where no child
covers it. For every icon (an instance, frame or group of at most 64px holding only vector
shapes), it checks the box, the turn, the drawn shape's box, the stroke and the colour. Lines,
edges and fills are read from a full-page picture, everything else from the page's own values. It
prints how many checks were met, lists every miss, and names what it doesn't compare. Zero-width
characters in Figma's copy are ignored.

Every value is compared exactly, at the precision the browser keeps. A length matches when it is
the same length in Chrome's layout steps of 1/64 px (Figma's 19.2px can only be laid out as
19.1875px). A CSS colour matches when each channel is Figma's value rounded to 8 bits. A drawn
pixel matches when it is one of the two 8-bit values either side of Figma's exact blend. Nothing
else is allowed: a value off by one step or more is a miss.

  python figma_check.py <page url or path> --file <figma file key> --frame <node id> [--frame <node id> ...]
                        [--root <css selector>] [--json <out.json>] [--shots <dir>] [--cache <dir>]
  python figma_check.py --frames --file <figma file key> --frame <node id> [--frame <node id> ...]
  python figma_check.py --selftest

--frames prints the lines a report opens with: each frame given, with its width, and "No phone
frame: the phone layout is not from the design." when none is narrower than 600. It reads the
frames as the check does but needs no browser, so it prints even where the check can't run.

Each --frame is measured at its own width, so pass the desktop frame and the phone frame (and any
other width the design draws). Figma values come from Figma's REST API with a personal access
token in FIGMA_TOKEN, and are cached in .figma-check/ (or --cache <dir>). Where the plugin's Figma
client is found (figma_client.py in FIGMA_CLIENT_DIR, else in the plugin's tools/ folder under
CLAUDE_PLUGIN_ROOT or three folders up from this script), the reads go through it and its token
lookup. --root measures one section of a longer page: its top-left corner stands for the frame's
top-left corner.

Exit codes: 0 every check met, 1 some checks missed, 2 the check could not run.
Needs Python 3.9+, `pip install playwright pillow` and `python -m playwright install chromium`.
"""
import argparse, base64, io, json, math, os, re, sys, urllib.request, urllib.parse

STEP = 1 / 64  # Chrome lays out in 1/64 px: lengths closer than this are the same length on the page
EXACT = 1e-3  # px: font size, line height and letter spacing are kept as decimals, not in steps
NEAR = 8  # px: how far from Figma's place an icon or line is looked for, to name how far off it is
NOT_COMPARED = ("corner radii, shadows and other effects, gradient and image fills, images, padding (seen "
                "only through where text, lines and edges land), the path of an icon's shape (two icons with "
                "the same box and stroke, such as a chevron up and down, can't be told apart), and vector "
                "shapes outside an icon")
HERE = os.path.dirname(os.path.abspath(__file__))


def same(a, b):
    return abs(a - b) < STEP


def equal(a, b):
    return abs(a - b) < EXACT


def c8(v):
    """A Figma colour channel (0..1) as the 8-bit value CSS writes."""
    return round(v * 255)


def fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


# ---------- Figma side ----------

def figma_get(path):
    """GET one Figma REST path, parsed. Where the plugin's Figma client is found (figma_client.py in
    FIGMA_CLIENT_DIR, else in tools/ under CLAUDE_PLUGIN_ROOT or three folders up from this script)
    the call goes through it: one rate budget with every other Figma tool on the machine, a 429
    waited out, each call logged; its token comes from figma_auth.py beside it. Anywhere else the
    call goes straight to the API with FIGMA_TOKEN."""
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    dirs = [os.environ.get("FIGMA_CLIENT_DIR"), plugin and os.path.join(plugin, "tools"),
            os.path.join(HERE, os.pardir, os.pardir, os.pardir, "tools")]
    d = next((x for x in dirs if x and os.path.exists(os.path.join(x, "figma_client.py"))), "")
    if d:
        if d not in sys.path:
            sys.path.append(d)
        import figma_client
        try:
            return figma_client.get(path, default_lane="batch", tool="figma_check")
        except figma_client.NoToken:
            raise SystemExit(f"could not run: no Figma token; `python {d}/figma_auth.py --source` says where it looked")
    token = os.environ.get("FIGMA_TOKEN")
    if not token:
        raise SystemExit("could not run: set FIGMA_TOKEN to a Figma personal access token")
    req = urllib.request.Request("https://api.figma.com/v1/" + path, headers={"X-Figma-Token": token})  # figma-client: allow (no shared client here)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_frames(file_key, ids, cache_dir=".figma-check"):
    """Figma REST nodes for these ids, cached on disk. Returns {id: document}."""
    os.makedirs(cache_dir, exist_ok=True)
    out, missing = {}, []
    for i in ids:
        f = os.path.join(cache_dir, f"{file_key}-{i.replace(':', '-')}.json")
        if os.path.exists(f):
            out[i] = json.load(open(f, encoding="utf-8"))
        else:
            missing.append(i)
    if missing:
        data = figma_get(f"files/{file_key}/nodes?" + urllib.parse.urlencode({"ids": ",".join(missing)}))
        for i in missing:
            node = (data.get("nodes") or {}).get(i)
            if not node:
                raise SystemExit(f"could not run: Figma returned nothing for frame {i}")
            out[i] = node["document"]
            json.dump(node["document"], open(os.path.join(cache_dir, f"{file_key}-{i.replace(':', '-')}.json"), "w", encoding="utf-8"))
    return out


PHONE_MAX = 600  # a frame narrower than this draws the phone layout
NO_BROWSER = ("could not run: Playwright isn't installed for this Python (pip install playwright pillow, then "
              "python -m playwright install chromium). --frames needs no browser and still lists the frames.")


def frame_lines(frames):
    """The lines a report opens with: the frames given, then one for the layout none of them draws."""
    given = "; ".join(f"{doc.get('name') or fid} ({fid}, {round(doc['absoluteBoundingBox']['width'])} wide)"
                      for fid, doc in frames.items())
    lines = [f"Frames: {given}."]
    if not any(doc["absoluteBoundingBox"]["width"] < PHONE_MAX for doc in frames.values()):
        lines.append("No phone frame: the phone layout is not from the design.")
    return lines


def norm(s):
    s = s.replace(" ", " ").replace(" ", " ")
    s = re.sub("[​‌‍⁠﻿]", "", s)  # zero-width characters print nothing
    return re.sub(r"\s+", " ", s).strip()


def frame_texts(doc):
    """Visible text layers of a frame, with values relative to the frame's top-left corner."""
    ox, oy = doc["absoluteBoundingBox"]["x"], doc["absoluteBoundingBox"]["y"]
    W, H = doc["absoluteBoundingBox"]["width"], doc["absoluteBoundingBox"]["height"]
    out = []

    def inside(bb, clip):
        if not clip:
            return True
        cx, cy, cw, ch = clip
        return bb["x"] < cx + cw and bb["x"] + bb["width"] > cx and bb["y"] < cy + ch and bb["y"] + bb["height"] > cy

    def walk(n, clip, op=1.0):
        if n.get("visible", True) is False or n.get("opacity", 1) == 0:
            return
        op = op * n.get("opacity", 1)  # layer opacity multiplies down the tree
        bb = n.get("absoluteBoundingBox")
        if bb and not inside(bb, clip):
            return
        if n["type"] == "TEXT":
            st = n.get("style", {})
            fills = [f for f in n.get("fills", []) if f.get("visible", True) and f.get("type") == "SOLID"]
            color = None
            if fills:
                c = fills[0]["color"]
                a = c.get("a", 1) * fills[0].get("opacity", 1) * op
                color = (c8(c["r"]), c8(c["g"]), c8(c["b"]), a)
            mixed = bool([x for x in n.get("characterStyleOverrides", []) if x])
            lh = st.get("lineHeightPx") if st.get("lineHeightUnit") != "INTRINSIC_%" else None
            out.append({"id": n["id"], "text": norm(n.get("characters", "")), "case": st.get("textCase"),
                        "size": st.get("fontSize"), "weight": st.get("fontWeight"), "lh": lh,
                        "ls": st.get("letterSpacing", 0), "color": color, "mixed": mixed,
                        "align": st.get("textAlignHorizontal", "LEFT"),
                        "x": bb["x"] - ox, "y": bb["y"] - oy, "w": bb["width"],
                        "h": bb["height"], "valign": st.get("textAlignVertical", "TOP")})
            return
        if bb and n.get("clipsContent"):
            nclip = (bb["x"], bb["y"], bb["width"], bb["height"])
            if clip:
                x1, y1 = max(clip[0], nclip[0]), max(clip[1], nclip[1])
                x2 = min(clip[0] + clip[2], nclip[0] + nclip[2]); y2 = min(clip[1] + clip[3], nclip[1] + nclip[3])
                nclip = (x1, y1, max(0, x2 - x1), max(0, y2 - y1))
            clip = nclip
        for c in n.get("children", []):
            walk(c, clip, op)

    root_clip = (ox, oy, W, H) if doc.get("clipsContent", True) else None
    for c in doc.get("children", []):
        walk(c, root_clip)
    return [t for t in out if t["text"]], (round(W), round(H))


SHAPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "POLYGON", "REGULAR_POLYGON", "ELLIPSE", "LINE", "RECTANGLE"}
BOXES = {"FRAME", "INSTANCE", "COMPONENT", "RECTANGLE"}  # drawn as a box: their strokes and fills are checked
ICON_MAX = 64
CAP = {"ROUND": "round", "SQUARE": "square", "NONE": "butt"}
JOIN = {"ROUND": "round", "BEVEL": "bevel", "MITER": "miter"}


def solid(paints, op=1.0):
    """The first visible solid paint as (r, g, b) floats 0..1 and its alpha, or None."""
    for p in paints or []:
        if p.get("visible", True) and p.get("type") == "SOLID":
            c = p["color"]
            return (c["r"], c["g"], c["b"]), c.get("a", 1) * p.get("opacity", 1) * op
    return None


def over(rgb, a, behind):
    return tuple(a * c + (1 - a) * b for c, b in zip(rgb, behind))


def rotation(n):
    """Degrees, counter-clockwise as Figma shows them. relativeTransform when the read has it;
    else REST's `rotation`, read as radians (Figma's REST docs don't state the unit)."""
    m = n.get("relativeTransform")
    if m:
        return math.degrees(math.atan2(-m[1][0], m[0][0]))
    return math.degrees(n.get("rotation", 0) or 0)


def frame_shapes(doc):
    """Visible lines, box edges, fills and icons of a frame, with values relative to the frame's
    top-left corner. A line is where Figma draws it (absoluteRenderBounds), with its stroke blended
    over the nearest solid fill behind it; a box's stroke is four such lines, corners left out. A
    fill is read at a point no child covers. An icon is an instance, frame or group of at most 64px
    whose visible descendants are all vector shapes."""
    ox, oy = doc["absoluteBoundingBox"]["x"], doc["absoluteBoundingBox"]["y"]
    lines, icons, fills = [], [], []

    def rel(bb):
        return [bb["x"] - ox, bb["y"] - oy, bb["width"], bb["height"]]

    def edges(n, bb, op, outside, inside):
        """A box's stroke as four lines, corners left out: where Figma draws each side for its
        stroke alignment, blended over what is behind that side."""
        st = solid(n.get("strokes"), op)
        if not st or st[1] <= 0:
            return
        each = n.get("individualStrokeWeights") or {}
        wt = {k: each.get(k, n.get("strokeWeight", 1)) for k in ("top", "right", "bottom", "left")}
        align = n.get("strokeAlign", "INSIDE")
        grow = {"OUTSIDE": 1.0, "CENTER": 0.5}.get(align, 0.0)
        x1, y1 = bb["x"] - wt["left"] * grow, bb["y"] - wt["top"] * grow
        x2, y2 = bb["x"] + bb["width"] + wt["right"] * grow, bb["y"] + bb["height"] + wt["bottom"] * grow
        R = max([n.get("cornerRadius", 0) or 0] + list(n.get("rectangleCornerRadii") or [])) + max(wt.values()) * grow
        under = outside if align == "OUTSIDE" else (inside if align == "INSIDE" else None)
        blend = st[0] if st[1] >= 1 else (over(st[0], st[1], under) if under else None)
        sides = {"top": (x1 + R, y1, x2 - x1 - 2 * R, wt["top"]), "bottom": (x1 + R, y2 - wt["bottom"], x2 - x1 - 2 * R, wt["bottom"]),
                 "left": (x1, y1 + R, wt["left"], y2 - y1 - 2 * R), "right": (x2 - wt["right"], y1 + R, wt["right"], y2 - y1 - 2 * R)}
        for side, (sx, sy, sw, sh) in sides.items():
            if wt[side] > 0 and max(sw, sh) > 2:
                lines.append({"kind": "edge", "id": n["id"], "name": f"{n.get('name', '')} {side} edge", "run": False,
                              "box": [sx - ox, sy - oy, sw, sh], "color": [v * 255 for v in blend] if blend else None})

    def fill_spot(n, bb, colour):
        """A point of a box's fill that no child covers: the middle of the widest band between the
        box's edge and its children, clear of the stroke and the corners. None when there is none."""
        kids = [c["absoluteBoundingBox"] for c in n.get("children", []) if shown(c) and c.get("absoluteBoundingBox")]
        x, y, w, h = bb["x"], bb["y"], bb["width"], bb["height"]
        if kids:
            ux1, uy1 = min(k["x"] for k in kids), min(k["y"] for k in kids)
            ux2, uy2 = max(k["x"] + k["width"] for k in kids), max(k["y"] + k["height"] for k in kids)
            bands = [(uy1 - y, (x + w / 2, (y + uy1) / 2)), (y + h - uy2, (x + w / 2, (uy2 + y + h) / 2)),
                     (ux1 - x, ((x + ux1) / 2, y + h / 2)), (x + w - ux2, ((ux2 + x + w) / 2, y + h / 2))]
        else:
            bands = [(min(w, h), (x + w / 2, y + h / 2))]
        r = max([n.get("cornerRadius", 0) or 0] + list(n.get("rectangleCornerRadii") or []))
        clear = (n.get("strokeWeight", 0) if solid(n.get("strokes")) else 0) + 1
        for size, (px, py) in sorted(bands, reverse=True):
            inside_corner = (min(px - x, x + w - px) < r and min(py - y, y + h - py) < r)
            if size >= 2 * clear and not inside_corner and all(not (k["x"] <= px <= k["x"] + k["width"] and k["y"] <= py <= k["y"] + k["height"]) for k in kids):
                fills.append({"kind": "fill", "id": n["id"], "name": n.get("name", ""), "at": [px - ox, py - oy],
                              "color": [v * 255 for v in colour]})
                return
        fills.append({"kind": "fill", "id": n["id"], "name": n.get("name", ""), "at": None,
                      "color": [v * 255 for v in colour]})

    def shown(n):
        return n.get("visible", True) is not False and n.get("opacity", 1) != 0

    def leaves(n):
        out = []
        for c in n.get("children", []):
            if shown(c):
                out += leaves(c) if c.get("children") else [c]
        return out

    def is_icon(n, bb):
        """The innermost instance, frame or group of at most 64px whose visible descendants are all
        vector shapes. A wrapper holding just one such container is not the icon; the container is."""
        kids = leaves(n)
        if not (n["type"] in ("INSTANCE", "FRAME", "GROUP", "COMPONENT") and bb and kids
                and 0 < bb["width"] <= ICON_MAX and 0 < bb["height"] <= ICON_MAX
                and all(k["type"] in SHAPES for k in kids)
                and any(k["type"] in ("VECTOR", "BOOLEAN_OPERATION") for k in kids)):
            return False
        inner = [c for c in n.get("children", []) if shown(c)]
        return not (len(inner) == 1 and inner[0]["type"] not in SHAPES and inner[0].get("children"))

    def walk(n, op, behind):
        if not shown(n):
            return
        op *= n.get("opacity", 1)
        outside = behind
        fill = solid(n.get("fills"))
        if fill and behind is not None:
            behind = over(fill[0], fill[1] * op, behind)
        elif fill and fill[1] * op >= 1:
            behind = fill[0]
        else:
            behind = behind if not fill else None
        bb = n.get("absoluteBoundingBox")
        if n["type"] in BOXES and bb and not is_icon(n, bb):
            edges(n, bb, op, outside, behind)
            if fill and fill[1] > 0:
                if behind is not None:
                    fill_spot(n, bb, behind)
                else:
                    fills.append({"kind": "fill", "id": n["id"], "name": n.get("name", ""), "at": None, "color": None})
        if n["type"] == "LINE":
            stroke, rb = solid(n.get("strokes"), op), n.get("absoluteRenderBounds")
            if stroke and rb and stroke[1] > 0:
                blend = stroke[0] if stroke[1] >= 1 else (over(stroke[0], stroke[1], behind) if behind else None)
                lines.append({"kind": "line", "id": n["id"], "name": n.get("name", ""), "box": rel(rb),
                              "color": [v * 255 for v in blend] if blend else None})
            return
        if is_icon(n, bb):
            kids = leaves(n)
            boxes = [k["absoluteBoundingBox"] for k in kids if k.get("absoluteBoundingBox")]
            x1, y1 = min(b["x"] for b in boxes), min(b["y"] for b in boxes)
            x2 = max(b["x"] + b["width"] for b in boxes); y2 = max(b["y"] + b["height"] for b in boxes)
            stroked = next((k for k in kids if solid(k.get("strokes"))), None)
            icon = {"kind": "icon", "id": n["id"], "name": n.get("name", ""), "box": rel(bb),
                    "rotation": rotation(n), "glyph": [x1 - ox, y1 - oy, x2 - x1, y2 - y1]}
            if stroked:
                rgb, a = solid(stroked.get("strokes"), op)
                icon["stroke"] = {"weight": stroked.get("strokeWeight", 1), "cap": CAP.get(stroked.get("strokeCap", "NONE"), "butt"),
                                  "join": JOIN.get(stroked.get("strokeJoin", "MITER"), "miter")}
                icon["color"] = [c8(v) for v in rgb] + [a]
            else:
                f = next((solid(k.get("fills"), op) for k in kids if solid(k.get("fills"))), None)
                icon["color"] = [c8(v) for v in f[0]] + [f[1]] if f else None
            icons.append(icon)
            return
        for c in n.get("children", []):
            walk(c, op, behind)

    walk(doc, 1.0, None)
    return lines, icons, fills


# ---------- page side ----------

JS = r"""
([texts, rootSel]) => {
  const norm = s => s.replace(/ /g,' ').replace(/[​-‍⁠﻿]/g,'').replace(/\s+/g,' ').trim();
  const root = rootSel ? document.querySelector(rootSel) : document.body;
  if (!root) return {error: 'root not found: ' + rootSel};
  const rr = root.getBoundingClientRect();
  const ox = rr.left + window.scrollX, oy = rr.top + window.scrollY;
  const visible = el => {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const els = [...root.querySelectorAll('*')].filter(e => !['SCRIPT','STYLE','svg','path'].includes(e.tagName));
  const allText = norm(root.innerText || '');
  const opacityChain = el => { let o = 1; for (let e = el; e; e = e.parentElement) o *= parseFloat(getComputedStyle(e).opacity); return o; };
  const res = [];
  // a string that appears more than once pairs up in reading order: the k-th layer in Figma
  // (top to bottom, then left to right) with the k-th matching element on the page
  const order = texts.map((t, i) => i).sort((a, b) => texts[a].y - texts[b].y || texts[a].x - texts[b].x);
  const nth = new Array(texts.length).fill(0), seen = {};
  for (const i of order) { const k = texts[i].text.toLowerCase(); nth[i] = seen[k] || 0; seen[k] = nth[i] + 1; }
  const pos = e => { const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.left)]; };
  for (const [ti, t] of texts.entries()) {
    const ci = !!t.case && t.case !== 'ORIGINAL';
    const eq = (a, b) => ci ? a.toLowerCase() === b.toLowerCase() : a === b;
    const has = (a, b) => ci ? a.toLowerCase().includes(b.toLowerCase()) : a.includes(b);
    const found = has(allText, t.text);
    let best = null;
    if (found) {
      const holds = els.filter(e => visible(e) && has(norm(e.innerText || ''), t.text));
      const deepest = holds.filter(e => ![...e.children].some(c => has(norm(c.innerText || ''), t.text)));
      const exact = deepest.filter(e => eq(norm(e.innerText || ''), t.text));
      const pool = (exact.length ? exact : deepest).sort((a, b) => { const pa = pos(a), pb = pos(b); return pa[0] - pb[0] || pa[1] - pb[1]; });
      best = pool[Math.min(nth[ti], pool.length - 1)] || null;
    }
    const row = {id: t.id, found};
    if (best) {
      const cs = getComputedStyle(best);
      const range = document.createRange(); range.selectNodeContents(best);
      const rects = [...range.getClientRects()].filter(r => r.width > 0 && r.height > 0);
      const er = best.getBoundingClientRect();
      // rendered size: computed size times every scale applied above it (transform, zoom)
      let sc = 1;
      for (let e = best; e && e !== document.documentElement; e = e.parentElement) {
        const ecs = getComputedStyle(e);
        if (ecs.transform && ecs.transform !== 'none') { const mx = new DOMMatrixReadOnly(ecs.transform); sc *= Math.hypot(mx.a, mx.b); }
        if (ecs.zoom && ecs.zoom !== 'normal' && parseFloat(ecs.zoom) !== 1) sc *= parseFloat(ecs.zoom);
      }
      const lh = cs.lineHeight === 'normal' ? null : parseFloat(cs.lineHeight);
      const left = rects.length ? Math.min(...rects.map(r => r.left)) : er.left;
      const right = rects.length ? Math.max(...rects.map(r => r.right)) : er.right;
      const first = rects.length ? rects.reduce((a, r) => r.top < a.top ? r : a) : er;
      // The first line's top is where its block lays it out: the block's content top, when the text
      // starts on the block's first line. Inferring it from the glyph box is half a pixel out
      // wherever Chrome rounds the leading, so that is only the fallback.
      let block = best;
      while (block.parentElement && getComputedStyle(block).display.startsWith('inline')) block = block.parentElement;
      const bcs = getComputedStyle(block), br = block.getBoundingClientRect();
      const contentTop = br.top + parseFloat(bcs.borderTopWidth) + parseFloat(bcs.paddingTop);
      const onFirst = lh && first.top >= contentTop - 0.01 && first.bottom <= contentTop + lh * sc + 0.01;
      const top = onFirst ? contentTop : (lh ? first.top - (lh * sc - first.height) / 2 : first.top);
      row.size = parseFloat(cs.fontSize) * sc;
      row.weight = parseInt(cs.fontWeight);
      row.lh = lh === null ? null : lh * sc;
      row.ls = cs.letterSpacing === 'normal' ? 0 : parseFloat(cs.letterSpacing) * sc;
      const m = cs.color.match(/rgba?\(([^)]+)\)/);
      const p = m ? m[1].split(/[ ,\/]+/).filter(Boolean).map(Number) : [0,0,0,1];
      row.color = [p[0], p[1], p[2], (p.length > 3 ? p[3] : 1) * opacityChain(best)];
      row.left = left + window.scrollX - ox;
      row.right = right + window.scrollX - ox;
      row.y = top + window.scrollY - oy;
      row.lines = new Set(rects.map(r => Math.round(r.top))).size || 1;
      row.smoothing = cs.webkitFontSmoothing || 'auto';
    }
    res.push(row);
  }
  return {res, height: Math.round(rr.height), origin: [ox, oy]};
}
"""

# The shapes an SVG draws: not those inside defs, a clip path, a mask or a symbol, which Figma's
# exports carry (a clip rect the size of the icon) but which draw nothing themselves.
DRAWN_JS = r"""
const drawn = svg => [...svg.querySelectorAll('path,line,polyline,polygon,circle,ellipse,rect')].filter(p => {
  for (let a = p.parentElement; a && a !== svg; a = a.parentElement)
    if (['defs', 'clippath', 'mask', 'symbol', 'pattern', 'marker'].includes(a.localName.toLowerCase())) return false;
  return true; });
"""

# Each Figma icon paired with the img, svg or image-painted element nearest its box (within NEAR px).
ICON_JS = r"""
([icons, rootSel, near]) => {
""" + DRAWN_JS + r"""
  const root = rootSel ? document.querySelector(rootSel) : document.body;
  const rr = root.getBoundingClientRect();
  const visible = el => {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const urlOf = cs => { const m = (cs.maskImage && cs.maskImage !== 'none' ? cs.maskImage : (cs.webkitMaskImage && cs.webkitMaskImage !== 'none' ? cs.webkitMaskImage : cs.backgroundImage)).match(/url\("?([^")]+)"?\)/); return m ? m[1] : null; };
  const cands = [...root.querySelectorAll('*')].filter(e => {
    const t = e.tagName.toLowerCase();
    if (t === 'img') return true;
    if (t === 'svg') return !(e.parentElement && e.parentElement.closest('svg'));
    if (e.closest('svg') || e.children.length) return false;
    return !!urlOf(getComputedStyle(e));
  }).filter(visible);
  const rel = r => [r.left - rr.left, r.top - rr.top, r.width, r.height];
  const turn = el => { let d = 0; for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const t = getComputedStyle(e).transform; if (t && t !== 'none') { const m = new DOMMatrixReadOnly(t); d += Math.atan2(m.b, m.a) * 180 / Math.PI; } }
    d = ((d % 360) + 540) % 360 - 180; return d === -180 ? 180 : d; };
  const used = new Set();
  return icons.map(ic => {
    let best = null, bestD = Infinity;
    for (const [i, e] of cands.entries()) {
      if (used.has(i)) continue;
      const b = rel(e.getBoundingClientRect());
      const d = Math.max(...b.map((v, k) => Math.abs(v - ic.box[k])));
      if (d < bestD) { bestD = d; best = i; }
    }
    if (best === null || bestD > near) return {found: false};
    used.add(best);
    const e = cands[best], t = e.tagName.toLowerCase(), cs = getComputedStyle(e), r = e.getBoundingClientRect();
    // a page turns clockwise for a positive angle, Figma counter-clockwise
    let op = 1; for (let a = e; a; a = a.parentElement) op *= parseFloat(getComputedStyle(a).opacity);
    const out = {found: true, tag: t, box: rel(r), rotation: -turn(e), size: [parseFloat(cs.width), parseFloat(cs.height)], opacity: op,
                 centre: [(r.left + r.right) / 2 - rr.left, (r.top + r.bottom) / 2 - rr.top]};
    if (t === 'svg') {
      const shapes = drawn(e);
      if (shapes.length) {
        const bs = shapes.map(s => s.getBoundingClientRect());
        const x1 = Math.min(...bs.map(b => b.left)), y1 = Math.min(...bs.map(b => b.top));
        out.glyph = [x1 - rr.left, y1 - rr.top, Math.max(...bs.map(b => b.right)) - x1, Math.max(...bs.map(b => b.bottom)) - y1];
        const s = shapes.find(s => getComputedStyle(s).stroke !== 'none') || null;
        if (s) { const ss = getComputedStyle(s), m = s.getScreenCTM();
          out.stroke = {weight: parseFloat(ss.strokeWidth) * Math.hypot(m.a, m.b), cap: ss.strokeLinecap, join: ss.strokeLinejoin, color: ss.stroke, opacity: parseFloat(ss.strokeOpacity)}; }
        else { const fs = getComputedStyle(shapes[0]); out.fill = {color: fs.fill, opacity: parseFloat(fs.fillOpacity)}; }
      }
    } else out.src = t === 'img' ? (e.currentSrc || e.src) : new URL(urlOf(cs), document.baseURI).href;
    return out;
  });
}
"""

# The drawn shape of an SVG file, in its own units: the box of its shapes, its viewBox and its stroke.
GLYPH_JS = r"""
(text) => {
""" + DRAWN_JS + r"""
  const d = document.createElement('div');
  d.style.cssText = 'position:absolute;left:0;top:0;visibility:hidden;pointer-events:none;color:#000';  // currentColor is black in an img
  d.innerHTML = text; document.body.appendChild(d);
  const s = d.querySelector('svg');
  if (!s) { d.remove(); return null; }
  const shapes = drawn(s);
  if (!shapes.length) { d.remove(); return null; }
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  for (const p of shapes) { const b = p.getBBox(); x1 = Math.min(x1, b.x); y1 = Math.min(y1, b.y); x2 = Math.max(x2, b.x + b.width); y2 = Math.max(y2, b.y + b.height); }
  const vb = s.viewBox && s.viewBox.baseVal && s.viewBox.baseVal.width ? s.viewBox.baseVal : null;
  const out = {bbox: [x1, y1, x2 - x1, y2 - y1], vb: vb ? [vb.x, vb.y, vb.width, vb.height] : [0, 0, parseFloat(s.getAttribute('width')), parseFloat(s.getAttribute('height'))],
               par: s.getAttribute('preserveAspectRatio') || 'xMidYMid meet'};
  const st = shapes.find(p => getComputedStyle(p).stroke !== 'none');
  if (st) { const c = getComputedStyle(st); out.stroke = {weight: parseFloat(c.strokeWidth), cap: c.strokeLinecap, join: c.strokeLinejoin, color: c.stroke, opacity: parseFloat(c.strokeOpacity)}; }
  else { const c = getComputedStyle(shapes[0]); out.fill = {color: c.fill, opacity: parseFloat(c.fillOpacity)}; }
  d.remove();
  return out;
}
"""

SCROLL = """async () => { const H = document.documentElement.scrollHeight;
  for (let y = 0; y < H; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
  window.scrollTo(0, 0); }"""


def expected_top(f, d):
    """Top of the first line in Figma: the box top, moved down when the text is centred or
    bottom-aligned inside a box taller than its lines."""
    if not f.get("lh") or f.get("valign", "TOP") == "TOP":
        return f["y"]
    spare = f["h"] - d.get("lines", 1) * f["lh"]
    if spare <= 0:
        return f["y"]
    return f["y"] + (spare / 2 if f["valign"] == "CENTER" else spare)


def compare(f, d):
    """One row's checks: name -> (met, expected, measured)."""
    checks = {"copy": (bool(d["found"]), f["text"][:60], "found" if d["found"] else "not on the page")}
    if not d.get("found") or "size" not in d or f["mixed"]:
        return checks
    if f["size"]:
        checks["size"] = (equal(d["size"], f["size"]), f"{fmt(f['size'])}px", f"{fmt(d['size'])}px")
    if f["weight"]:
        checks["weight"] = (d["weight"] == f["weight"], str(f["weight"]), str(d["weight"]))
    if f["lh"] is not None:
        checks["line height"] = (d["lh"] is not None and equal(d["lh"], f["lh"]), f"{fmt(f['lh'])}px",
                                 f"{fmt(d['lh'])}px" if d["lh"] is not None else "normal")
    ls = f["ls"] or 0
    checks["letter spacing"] = (equal(d["ls"], ls), f"{fmt(ls)}px", f"{fmt(d['ls'])}px")
    if f["color"]:
        fc, dc = f["color"], d["color"]
        ok = list(fc[:3]) == [round(v) for v in dc[:3]] and c8(fc[3]) == c8(dc[3])
        checks["colour"] = (ok, "rgba(%d,%d,%d,%.3f)" % tuple(fc), "rgba(%d,%d,%d,%.3f)" % tuple(dc))
    if f["align"] == "CENTER":
        dx, edge = (d["left"] + d["right"]) / 2 - (f["x"] + f["w"] / 2), "centre"
    elif f["align"] == "RIGHT":
        dx, edge = d["right"] - (f["x"] + f["w"]), "right edge"
    else:
        dx, edge = d["left"] - f["x"], "left edge"
    checks["across"] = (abs(dx) < STEP, f"{edge} as designed", f"{'+' if dx > 0 else ''}{fmt(dx)}px off")
    top = expected_top(f, d)
    dy = d["y"] - top
    checks["down"] = (abs(dy) < STEP, f"top at {fmt(top)}px", f"{'+' if dy > 0 else ''}{fmt(dy)}px off")
    # Figma draws text with greyscale antialiasing. Without this, Chromium on a Mac draws light text
    # on a dark fill visibly heavier than the design, which no value above can show.
    checks["smoothing"] = (d.get("smoothing") == "antialiased", "antialiased, as Figma draws text", d.get("smoothing") or "auto")
    return checks


def box_text(b):
    return f"{fmt(b[0])},{fmt(b[1])} {fmt(b[2])}x{fmt(b[3])}"


def compare_line(f, img, origin):
    """Where the page draws Figma's line, from the full-page picture: the rows (columns, for an
    upright line) within NEAR px whose pixels across the run match each other and differ from the
    rows either side, the colour drawn there, and how far the run reaches."""
    x, y, w, h = f["box"]
    flat = w >= h
    px, (W, H) = img.load(), img.size
    a0, a1 = (round(origin[1] + y), round(origin[1] + y + h)) if flat else (round(origin[0] + x), round(origin[0] + x + w))
    s0, s1 = (round(origin[0] + x), round(origin[0] + x + w)) if flat else (round(origin[1] + y), round(origin[1] + y + h))
    lim_a, lim_s = (H, W) if flat else (W, H)
    get = (lambda a, s: px[s, a]) if flat else (lambda a, s: px[a, s])
    word = "rows" if flat else "columns"
    span = lambda lo, hi: f"{word} {lo}-{hi - 1}" if hi - lo > 1 else f"{word[:-1]} {lo}"
    samples = sorted({min(lim_s - 1, max(0, s0 + 1 + i * max(0, s1 - s0 - 3) // 6)) for i in range(7)})
    window = range(max(0, a0 - NEAR), min(lim_a, a1 + NEAR))
    # runs of rows that are one colour all the way across the samples; the line is a thin run whose
    # colour differs from the runs either side of it
    runs = []
    for a in window:
        cols = {get(a, s) for s in samples}
        key = cols.pop() if len(cols) == 1 else None
        if runs and key is not None and runs[-1][0] == key:
            runs[-1][1].append(a)
        else:
            runs.append([key, [a]])
    thin = max(4, a1 - a0 + 2)
    found = [r[1] for i, r in enumerate(runs) if r[0] is not None and len(r[1]) <= thin and 0 < i < len(runs) - 1
             and runs[i - 1][0] != r[0] and runs[i + 1][0] != r[0]]
    if not found:
        return {"line place": (False, span(a0, a1), f"no line drawn within {NEAR}px")}
    g = min(found, key=lambda g: abs(g[0] - a0))
    checks = {"line place": ((g[0], g[-1] + 1) == (a0, a1), span(a0, a1), span(g[0], g[-1] + 1))}
    mid_a, mid_s = g[len(g) // 2], samples[len(samples) // 2]
    got = get(mid_a, mid_s)
    if f.get("color"):
        e = f["color"]
        checks["line colour"] = (all(abs(v - c) < 1 for v, c in zip(got, e)), "rgb(%s)" % ",".join(fmt(c) for c in e),
                                 "rgb(%d,%d,%d)" % got)
    if f.get("run", True):  # a box edge runs on into its corners, so only a line's run is measured
        lo = hi = mid_s
        while lo - 1 >= 0 and get(mid_a, lo - 1) == got:
            lo -= 1
        while hi + 1 < lim_s and get(mid_a, hi + 1) == got:
            hi += 1
        along = "across" if flat else "down"
        checks["line run"] = ((lo, hi + 1) == (s0, s1), f"{along} {s0}-{s1 - 1}", f"{along} {lo}-{hi}")
    return checks


def compare_fill(f, img, origin):
    """A box's fill, read from the full-page picture at a point no child covers."""
    if not f.get("color"):
        return {"fill": (False, "the box's fill", "unreadable: it is see-through over nothing Figma states")}
    if not f.get("at"):
        return {"fill": (False, "rgb(%s)" % ",".join(fmt(c) for c in f["color"]), "unreadable: no point of it is clear of its children")}
    x, y = int(origin[0] + f["at"][0]), int(origin[1] + f["at"][1])
    if not (0 <= x < img.size[0] and 0 <= y < img.size[1]):
        return {"fill": (False, "the box's fill", "outside the page")}
    got, e = img.getpixel((x, y)), f["color"]
    return {"fill": (all(abs(v - c) < 1 for v, c in zip(got, e)), "rgb(%s) at %d,%d" % (",".join(fmt(c) for c in e), x, y),
                     "rgb(%d,%d,%d)" % got)}


def svg_text(src):
    """The text of an icon's SVG file, or None when it isn't an SVG the check can open."""
    try:
        if src.startswith("data:"):
            head, _, body = src.partition(",")
            text = base64.b64decode(body).decode("utf-8") if ";base64" in head else urllib.parse.unquote(body)
        elif src.startswith("file:"):
            with open(urllib.request.url2pathname(urllib.parse.urlparse(src).path), encoding="utf-8") as fh:
                text = fh.read()
        elif src.startswith(("http:", "https:")):
            with urllib.request.urlopen(src, timeout=30) as r:
                text = r.read().decode("utf-8")
        else:
            return None
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return text if "<svg" in text else None


def place_glyph(g, d):
    """Put an SVG file's shape box and stroke where the page draws them: into the element's box by
    the file's viewBox and preserveAspectRatio, then through the element's turn about its centre."""
    vx, vy, vw, vh = g["vb"]
    W, H = d["size"]
    par = g["par"].split()
    if par[0] == "none":
        sx, sy, tx, ty = W / vw, H / vh, 0.0, 0.0
    else:
        s = (max if len(par) > 1 and par[1] == "slice" else min)(W / vw, H / vh)
        sx = sy = s
        tx = {"xMin": 0.0, "xMid": (W - vw * s) / 2, "xMax": W - vw * s}.get(par[0][:4], (W - vw * s) / 2)
        ty = {"YMin": 0.0, "YMid": (H - vh * s) / 2, "YMax": H - vh * s}.get(par[0][4:], (H - vh * s) / 2)
    gx, gy, gw, gh = g["bbox"]
    x1, y1 = tx + (gx - vx) * sx, ty + (gy - vy) * sy
    t = math.radians(-d["rotation"])  # the page's clockwise turn
    cx, cy = W / 2, H / 2
    pts = [(cx + (px - cx) * math.cos(t) - (py - cy) * math.sin(t), cy + (px - cx) * math.sin(t) + (py - cy) * math.cos(t))
           for px in (x1, x1 + gw * sx) for py in (y1, y1 + gh * sy)]
    left, top = d["centre"][0] - W / 2, d["centre"][1] - H / 2
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    d["glyph"] = [left + min(xs), top + min(ys), max(xs) - min(xs), max(ys) - min(ys)]
    if g.get("stroke"):
        d["stroke"] = dict(g["stroke"], weight=g["stroke"]["weight"] * sx)
    if g.get("fill"):
        d["fill"] = g["fill"]


def css_rgba(paint):
    m = re.match(r"rgba?\(([^)]+)\)", (paint or {}).get("color", ""))
    if not m:
        return None
    p = [float(v) for v in re.split(r"[ ,/]+", m.group(1).strip()) if v]
    return [round(p[0]), round(p[1]), round(p[2]), (p[3] if len(p) > 3 else 1) * paint.get("opacity", 1)]


def compare_icon(f, d):
    if not d.get("found"):
        return {"icon": (False, f"an img or svg at {box_text(f['box'])}", f"none within {NEAR}px")}
    checks = {"icon box": (all(same(a, b) for a, b in zip(d["box"], f["box"])), box_text(f["box"]), box_text(d["box"]))}
    turn = ((d["rotation"] - f["rotation"] + 180) % 360) - 180
    deg = lambda v: fmt(abs(v) if abs(abs(v) - 180) < 1e-9 else v)
    checks["icon turn"] = (abs(turn) < 1e-3, f"{deg(f['rotation'])}°", f"{deg(d['rotation'])}°")
    if d.get("glyph"):
        checks["drawn shape"] = (all(same(a, b) for a, b in zip(d["glyph"], f["glyph"])), box_text(f["glyph"]), box_text(d["glyph"]))
    else:
        checks["drawn shape"] = (False, box_text(f["glyph"]), "unreadable: not an SVG the check can open")
    fs, ds = f.get("stroke"), d.get("stroke")
    say = lambda s: f"{fmt(s['weight'])}px {s['cap']} cap, {s['join']} join" if s else "no stroke"
    if fs or ds:
        ok = bool(fs and ds) and same(fs["weight"], ds["weight"]) and fs["cap"] == ds["cap"] and fs["join"] == ds["join"]
        checks["stroke"] = (ok, say(fs), say(ds))
    if f.get("color"):
        got = css_rgba(ds if fs else d.get("fill"))
        if got:
            got[3] *= d.get("opacity", 1)
        fc = f["color"]
        ok = bool(got) and list(fc[:3]) == got[:3] and c8(fc[3]) == c8(got[3])
        checks["icon colour"] = (ok, "rgba(%d,%d,%d,%.3f)" % tuple(fc), ("rgba(%d,%d,%d,%.3f)" % tuple(got)) if got else "unreadable")
    return checks


def check(url, frames, root=None, shots=None, plant=None):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    if "://" not in url:
        p = os.path.abspath(url)
        url = "file://" + (os.path.join(p, "index.html") if os.path.isdir(p) else p)
    report = {"url": url, "frames": [], "not_compared": NOT_COMPARED}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for fid, doc in frames.items():
            texts, (W, H) = frame_texts(doc)
            lines, icons, fills = frame_shapes(doc)
            fr = {"frame": fid, "name": doc.get("name"), "width": W, "height": H, "texts": len(texts),
                  "lines": sum(1 for f in lines if f["kind"] == "line"), "edges": sum(1 for f in lines if f["kind"] == "edge"),
                  "icons": len(icons), "fills": len(fills), "rows": []}
            pg = br.new_page(viewport={"width": W, "height": 900}, reduced_motion="reduce")
            try:
                pg.goto(url, wait_until="load", timeout=30000)
                pg.evaluate("document.fonts.ready.then(() => true)")
                pg.evaluate(SCROLL)
                if root:
                    pg.locator(root).first.scroll_into_view_if_needed()
                if plant:
                    pg.evaluate(plant)
                pg.wait_for_timeout(500)
                dom = pg.evaluate(JS, [texts, root])
                if "error" in dom:
                    raise RuntimeError(dom["error"])
                found = pg.evaluate(ICON_JS, [[{"box": i["box"]} for i in icons], root, NEAR]) if icons else []
                for d in found:
                    text = svg_text(d["src"]) if d.get("src") else None
                    g = pg.evaluate(GLYPH_JS, text) if text else None
                    if g:
                        place_glyph(g, d)
                picture = Image.open(io.BytesIO(pg.screenshot(full_page=True))).convert("RGB") if (lines or fills) else None
                if shots:
                    os.makedirs(shots, exist_ok=True)
                    shot = os.path.join(shots, f"build-{W}.png")
                    (pg.locator(root).first.screenshot(path=shot) if root else pg.screenshot(path=shot, full_page=True))
                    fr["screenshot"] = shot
            except Exception as e:  # noqa: BLE001
                fr["error"] = str(e)[:300]
                report["frames"].append(fr)
                pg.close()
                continue
            fr["page_height"] = dom["height"]
            for f, d in zip(texts, dom["res"]):
                fr["rows"].append({"text": f["text"], "figma_id": f["id"], "checks": compare(f, d)})
            for f in lines:
                fr["rows"].append({"text": f"{f['name']} ({f['kind']})", "figma_id": f["id"], "checks": compare_line(f, picture, dom["origin"])})
            for f in fills:
                fr["rows"].append({"text": f"{f['name']} (fill)", "figma_id": f["id"], "checks": compare_fill(f, picture, dom["origin"])})
            for f, d in zip(icons, found):
                fr["rows"].append({"text": f"{f['name']} (icon)", "figma_id": f["id"], "checks": compare_icon(f, d)})
            pg.close()
            report["frames"].append(fr)
        br.close()
    met = tot = 0
    for fr in report["frames"]:
        fr["met"] = sum(1 for r in fr["rows"] for v in r["checks"].values() if v[0])
        fr["total"] = sum(len(r["checks"]) for r in fr["rows"])
        met += fr["met"]
        tot += fr["total"]
    report["met"], report["total"] = met, tot
    report["could_not_run"] = [fr["frame"] for fr in report["frames"] if "error" in fr]
    return report


def print_report(rep, out=sys.stdout):
    w = out.write
    status = "could not run" if rep["could_not_run"] else ("every check met" if rep["met"] == rep["total"] else "checks missed")
    w(f"figma-check: {rep['met']} of {rep['total']} checks met ({status}), every value compared exactly\n")
    w(f"Not compared: {rep.get('not_compared', NOT_COMPARED)}.\n")
    for fr in rep["frames"]:
        if "error" in fr:
            w(f"\n{fr['width']} wide, frame {fr['frame']}: COULD NOT RUN: {fr['error']}\n")
            continue
        w(f"\n{fr['width']} wide, frame {fr['frame']} ({fr['name']}): {fr['met']} of {fr['total']} met over"
          f" {fr['texts']} texts, {fr.get('lines', 0)} lines, {fr.get('edges', 0)} box edges, {fr.get('fills', 0)} fills"
          f" and {fr.get('icons', 0)} icons,"
          f" page {fr['page_height']}px tall against {fr['height']}px in Figma\n")
        for r in fr["rows"]:
            for name, (ok, exp, got) in r["checks"].items():
                if not ok:
                    w(f"  MISS  {name:14} \"{r['text'][:44]}\"  expected {exp}, got {got}\n")


# ---------- self-test ----------

PLANTS = [
    ("heading size", "document.querySelector('h1').style.fontSize='44px'", "size"),
    ("retyped copy", "document.querySelector('.lede').textContent='A rewritten line that is not the design copy.'", "copy"),
    ("wrong colour", "document.querySelector('.lede').style.color='#000000'", "colour"),
    ("letter spacing", "document.querySelector('.card h2').style.letterSpacing='1px'", "letter spacing"),
    ("weight", "document.querySelector('.card h2').style.fontWeight='400'", "weight"),
    ("moved across", "document.querySelector('.card').style.marginLeft='40px'", "across"),
    ("font smoothing", "document.documentElement.style.setProperty('-webkit-font-smoothing','auto')", "smoothing"),
    # each of these was inside the old tolerances, or outside what the check looked at
    ("heading 0.3px too big", "document.querySelector('h1').style.fontSize='48.3px'", "size"),
    ("letter spacing -0.39px for -0.4px", "document.querySelector('h1').style.letterSpacing='-0.39px'", "letter spacing"),
    ("card 1px across", "document.querySelector('.card').style.marginLeft='1px'", "across"),
    ("divider 1px low", "document.querySelector('.rule').style.top='57px'", "line place"),
    ("divider 1px short", "document.querySelector('.rule').style.right='25px'", "line run"),
    ("card outline drawn inside", "(c => { c.style.outline='none'; c.style.boxShadow='inset 0 0 0 1px #e4e4e7'; })(document.querySelector('.card'))", "line place"),
    ("card fill one step off", "document.querySelector('.card').style.background='#f4f4f6'", "fill"),
    ("icon turned 180 degrees", "document.querySelector('.icon').style.transform='rotate(180deg)'", "icon turn"),
    ("icon 1px across", "document.querySelector('.icon').style.right='25px'", "icon box"),
    ("icon stroke 2.5px", "document.querySelector('.icon').src='data:image/svg+xml,' + encodeURIComponent('<svg width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M6 9L12 15L18 9\" stroke=\"#111113\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>')", "stroke"),
    ("icon at half opacity", "document.querySelector('.icon').style.opacity='0.5'", "icon colour"),
]


def selftest():
    fx = os.path.join(HERE, "selftest")
    frames = json.load(open(os.path.join(fx, "figma.json"), encoding="utf-8"))
    page = os.path.join(fx, "page.html")
    good = check(page, frames)
    ok_good = good["met"] == good["total"] and not good["could_not_run"]
    caught = 0
    lines = []
    for name, js, kind in PLANTS:
        rep = check(page, frames, plant=js)
        missed_kinds = {n for fr in rep["frames"] for r in fr["rows"] for n, v in r["checks"].items() if not v[0]}
        hit = kind in missed_kinds
        caught += hit
        lines.append(f"  {'caught' if hit else 'MISSED'}  {name}")
    print("\n".join(lines))
    if not ok_good:
        print_report(good)
    print(f"{caught} of {len(PLANTS)} planted mistakes caught; known good page "
          f"{'passed' if ok_good else 'FAILED'} ({good['met']} of {good['total']})")
    return 0 if (ok_good and caught == len(PLANTS)) else 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--frame", action="append", default=[])
    ap.add_argument("--root")
    ap.add_argument("--json")
    ap.add_argument("--shots")
    ap.add_argument("--cache", default=".figma-check")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--frames", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        try:
            return selftest()
        except ImportError:
            print(NO_BROWSER)
            return 2
    if a.frames:
        if not (a.file and a.frame):
            ap.error("--frames needs --file and at least one --frame")
        try:
            print("\n".join(frame_lines(fetch_frames(a.file, a.frame, a.cache))))
        except (SystemExit, OSError, ValueError, KeyError) as e:
            print(f"Frames: {', '.join(a.frame)}, widths unknown: {e}")
            return 2
        return 0
    if not (a.page and a.file and a.frame):
        ap.error("give a page, --file and at least one --frame (or --selftest)")
    try:
        frames = fetch_frames(a.file, a.frame, a.cache)
        rep = check(a.page, frames, a.root, a.shots)
    except SystemExit as e:
        print(str(e))
        return 2
    except ImportError:
        print(NO_BROWSER)
        return 2
    print_report(rep)
    if a.json:
        json.dump(rep, open(a.json, "w", encoding="utf-8"), indent=1)
    if rep["could_not_run"]:
        return 2
    return 0 if rep["met"] == rep["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
