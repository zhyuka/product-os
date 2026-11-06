
  const out = [];
  const split = (text, at) => {  // [piece, the at character after it], split outside quotes and ()
    const out = []; let depth = 0, quote = null, from = 0;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (quote) { if (c === "\\") i++; else if (c === quote) quote = null; }
      else if (c === '"' || c === "'") quote = c;
      else if (c === "(") depth++;
      else if (c === ")") depth = Math.max(0, depth - 1);
      else if (!depth && at.includes(c)) { out.push([text.slice(from, i), c]); from = i + 1; }
    }
    out.push([text.slice(from), ""]);
    return out;
  };
  const load = src => new Promise(done => {
    const img = new Image(); img.onload = () => done(img); img.onerror = () => done(null); img.src = src; });
  const vector = src => /\.svg($|[?#])|^data:image\/svg/i.test(src);
  const blurry = (w, h, nw, nh) => Math.max(w / nw, h / nh) * scale > BLUR;
  const needs = (w, h) => [Math.ceil(w * scale), Math.ceil(h * scale)];
  // An SVG scales, but a picture inside one doesn't: each <image> it holds is drawn at the size
  // the SVG is drawn at, w by h, and judged like any other picture.
  const inSvg = async (src, w, h) => {
    let svg;
    try { const text = await fetch(src).then(r => r.ok ? r.text() : "");
          svg = new DOMParser().parseFromString(text, "image/svg+xml").documentElement; } catch (e) { return []; }
    if (!svg || svg.localName !== "svg") return [];
    const box = (svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
    const [vw, vh] = box.length === 4 && box[2] > 0 && box[3] > 0 ? [box[2], box[3]]
      : [parseFloat(svg.getAttribute("width")), parseFloat(svg.getAttribute("height"))];
    if (!(vw > 0 && vh > 0)) return [];
    const k = Math.min(w / vw, h / vh), found = [];
    for (const image of svg.querySelectorAll("image")) {
      const href = image.getAttribute("href") || image.getAttributeNS("http://www.w3.org/1999/xlink", "href");
      const iw = parseFloat(image.getAttribute("width")) * k, ih = parseFloat(image.getAttribute("height")) * k;
      if (!href) continue;
      // An SVG drawn as an image loads nothing it links to; only a picture inside it as data shows.
      if (!/^data:/i.test(href)) { found.push({broken: true, inner: src, href}); continue; }
      if (!(iw > 0 && ih > 0)) continue;
      const pic = await load(new URL(href, new URL(src, location.href)).href);
      if (pic && blurry(iw, ih, pic.naturalWidth, pic.naturalHeight))
        found.push({width: Math.round(iw), height: Math.round(ih), natural: [pic.naturalWidth, pic.naturalHeight],
                    needs: needs(iw, ih), inner: src});
    }
    return found;
  };
  // A CSS background: the first layer with a picture, drawn at the size that layer's
  // background-size gives it. In an image-set(), the one the browser picks at this density: the
  // least dense that's dense enough, else the densest. A fixed background is sized against the
  // screen, not its box.
  for (const el of deepAll("*", document.body)) {
    const style = getComputedStyle(el);
    if (!style.backgroundImage || style.backgroundImage === "none" || !shown(el)) continue;
    const layers = split(style.backgroundImage, ",").map(([l]) => l.trim());
    const n = layers.findIndex(l => /url\(/.test(l));
    if (n < 0) continue;
    const layer = (value, i) => { const all = split(value, ",").map(([v]) => v.trim()); return all[i % all.length]; };
    const bg = layers[n];
    let src, density = 1, set = bg.includes("image-set(");
    if (set) {
      const options = [...bg.matchAll(/url\(["']?(.*?)["']?\)\s*([\d.]+)?(?:x|dppx)?/g)]
        .map(m => [m[1], parseFloat(m[2]) || 1]).sort((a, b) => a[1] - b[1]);
      if (!options.length) continue;
      [src, density] = options.find(o => o[1] >= scale) || options[options.length - 1];
    } else {
      const m = bg.match(/url\(["']?(.*?)["']?\)/);
      if (!m) continue;
      src = m[1];
    }
    const img = await load(src);
    if (!img) { out.push({path: pathOf(el), src, broken: true, background: true, chosen: set ? density : null}); continue; }
    const fixed = layer(style.backgroundAttachment, n) === "fixed";
    const r = fixed ? {width: innerWidth, height: innerHeight} : el.getBoundingClientRect();
    // Its pixels, and its size on the page before background-size, which density divides.
    const nw = img.naturalWidth, nh = img.naturalHeight, iw = nw / density, ih = nh / density;
    const size = layer(style.backgroundSize, n);
    let w, h;
    if (size === "cover" || size === "contain") {
      const k = (size === "cover" ? Math.max : Math.min)(r.width / iw, r.height / ih);
      w = iw * k; h = ih * k;
    } else {
      const [a, b = "auto"] = size.split(/\s+/);
      const length = (v, box) => v === "auto" ? null : v.endsWith("%") ? box * parseFloat(v) / 100 : parseFloat(v);
      w = length(a, r.width); h = length(b, r.height);
      if (w === null && h === null) { w = iw; h = ih; }
      else if (w === null) w = iw * h / ih;
      else if (h === null) h = ih * w / iw;
    }
    if (vector(src))
      (await inSvg(src, w, h)).forEach(f => out.push({path: pathOf(el), src, ...f}));
    else if (blurry(w, h, nw, nh))
      out.push({path: pathOf(el), src, width: Math.round(w), height: Math.round(h),
                natural: [nw, nh], needs: needs(w, h), background: true});
  }
  // A mask whose file doesn't load hides all of what it masks, so a picture under one never shows.
  for (const el of deepAll("*", document.body)) {
    const style = getComputedStyle(el), m = (style.maskImage || style.webkitMaskImage || "").match(/url\(["']?(.*?)["']?\)/);
    if (!m || !el.checkVisibility({visibilityProperty: true})) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || !(["img", "canvas", "svg", "video"].includes(el.localName)
        || /url\(/.test(style.backgroundImage) || el.querySelector("img, canvas, svg, video"))) continue;
    if (!(await load(m[1]))) out.push({path: pathOf(el), src: m[1], broken: true, mask: true});
  }
  // A picture that loaded and takes up room, but that opacity 0 keeps from ever showing: a fade-in
  // that never ran, say. Not one with another picture shown over the same spot, as in a carousel
  // that fades between slides, and not one the pointer passes through, as in a closed panel. A
  // hover that shows it is tried after this.
  const pictureAt = (x, y, self) => document.elementsFromPoint(x, y).some(e => e !== self && !e.contains(self)
    && shown(e) && (["img", "canvas", "video", "svg"].includes(e.localName) || /url\(/.test(getComputedStyle(e).backgroundImage)));
  for (const img of deepAll("img")) {
    let r = img.getBoundingClientRect();
    if (!(img.complete && img.naturalWidth && r.width > 1 && r.height > 1 && !shown(img)
          && img.checkVisibility({visibilityProperty: true}) && getComputedStyle(img).pointerEvents !== "none")) continue;
    img.scrollIntoView({block: "center"});  // elementsFromPoint sees only the screen
    r = img.getBoundingClientRect();
    if (!pictureAt(r.x + r.width / 2, r.y + r.height / 2, img))
      out.push({path: pathOf(img), src: img.currentSrc || img.src, unseen: true});
  }
  scrollTo(0, 0);
  for (const img of deepAll("img")) {
    if (!shown(img)) continue;
    const src = img.currentSrc || img.src;
    if (img.complete && img.naturalWidth === 0) { out.push({path: pathOf(img), src, broken: true}); continue; }
    if (!img.complete) continue;
    const r = img.getBoundingClientRect(), fit = getComputedStyle(img).objectFit;
    const nw = img.naturalWidth, nh = img.naturalHeight, sx = r.width / nw, sy = r.height / nh;
    // The size the picture itself is drawn at: the box, or scaled to cover or fit inside it.
    const k = fit === "cover" ? Math.max(sx, sy) : fit === "contain" ? Math.min(sx, sy)
      : fit === "scale-down" ? Math.min(1, sx, sy) : fit === "none" ? 1 : null;
    const [w, h] = k === null ? [r.width, r.height] : [nw * k, nh * k];
    if (vector(src))
      (await inSvg(src, w, h)).forEach(f => out.push({path: pathOf(img), src, ...f}));
    else if (blurry(w, h, nw, nh))
      out.push({path: pathOf(img), src, width: Math.round(r.width), height: Math.round(r.height),
                natural: [nw, nh], needs: needs(w, h), cropped: w > r.width + 1 || h > r.height + 1});
  }
  // A picture an SVG on the page holds, fitted inside its box as an SVG fits one.
  for (const image of deepAll("svg image")) {
    if (!shown(image)) continue;
    const src = new URL(image.getAttribute("href") || image.getAttributeNS("http://www.w3.org/1999/xlink", "href")
                        || "", document.baseURI).href;
    const pic = await load(src);
    if (!pic) { out.push({path: pathOf(image), src, broken: true}); continue; }
    const r = image.getBoundingClientRect(), nw = pic.naturalWidth, nh = pic.naturalHeight;
    const k = Math.min(r.width / nw, r.height / nh);
    if (blurry(nw * k, nh * k, nw, nh))
      out.push({path: pathOf(image), src, width: Math.round(nw * k), height: Math.round(nh * k),
                natural: [nw, nh], needs: needs(nw * k, nh * k)});
  }
  // A canvas has as many pixels as its buffer, whatever size it's drawn at.
  for (const canvas of deepAll("canvas")) {
    const r = canvas.getBoundingClientRect();
    if (shown(canvas) && canvas.width && canvas.height && blurry(r.width, r.height, canvas.width, canvas.height))
      out.push({path: pathOf(canvas), canvas: true, width: Math.round(r.width), height: Math.round(r.height),
                natural: [canvas.width, canvas.height], needs: needs(r.width, r.height)});
  }
  // CSS the browser drops, since it isn't valid: an unquoted url() with a space in it, so the
  // background is never drawn, or an aspect-ratio of 2:1, so the box with the picture is 0 px
  // tall. Nothing loads or fails, so only the CSS as written shows it. Each declaration is
  // checked with the browser's own parser.
  // [name, value] of each declaration that isn't valid. A vendor prefix or a custom property is
  // left alone, since another browser, or a var() later, may read it.
  const declarations = text => split(text, ";").map(([d]) => { const i = d.indexOf(":");
    return i < 0 ? null : [d.slice(0, i).trim().toLowerCase(), d.slice(i + 1).trim()]; }).filter(d => d && d[0] && d[1]);
  const valid = ([name, value]) => CSS.supports(name, value.replace(/!\s*important$/i, ""));
  const dropped = text => declarations(text).filter(d => !d[0].startsWith("-") && !valid(d));
  // A background picture a later background in the same block replaces with one that has none:
  // a gradient written after the shorthand, say. [name, value, later name, later value].
  const isBackground = name => /^background(-image)?$/.test(name);
  const replaced = text => { const all = declarations(text).filter(d => isBackground(d[0]) && valid(d));
    return all.flatMap((d, i) => {
      const later = /url\(/i.test(d[1]) && all.slice(i + 1).find(e => !/url\(/i.test(e[1]));
      return later ? [[d[0], d[1], later[0], later[1]]] : []; }); };
  const rules = text => {  // [selector, body] of each block that holds no block
    const out = [], open = []; let head = "";
    for (const [piece, end] of split(text.replace(/\/\*[\s\S]*?\*\//g, ""), "{};")) {
      if (end === "{") { open.push({head: (head + piece).trim(), body: "", inner: false}); head = ""; }
      else if (end === ";") { if (open.length) open[open.length - 1].body += piece + ";"; else head = ""; }
      else if (end === "}") { const b = open.pop(); if (!b) continue; b.body += piece;
        if (!b.inner) out.push([b.head, b.body]); if (open.length) open[open.length - 1].inner = true; }
    }
    return out;
  };
  // A dropped declaration counts where it costs a picture: a background that's then never drawn,
  // or any other on an element with a picture that's then drawn with no width or no height.
  const named = new Set(out.map(o => o.path));
  const pictured = el => ["img", "canvas", "svg", "video"].includes(el.localName)
    || /url\(/.test(getComputedStyle(el).backgroundImage);
  const report = (el, [name, value]) => {
    const path = pathOf(el), r = el.getBoundingClientRect();
    if (named.has(path) || !el.checkVisibility({visibilityProperty: true})) return;
    const background = /^background(-image)?$/.test(name) && /url\(/i.test(value);
    if (background ? shown(el) && getComputedStyle(el).backgroundImage === "none"
                   : pictured(el) && (r.width < 1 || r.height < 1)) {
      named.add(path);
      out.push({path, invalid: true, name, value, size: background ? null : [Math.round(r.width), Math.round(r.height)]});
    }
  };
  const lost = (el, [name, value, laterName, laterValue]) => { const path = pathOf(el);
    if (!named.has(path) && shown(el) && !/url\(/.test(getComputedStyle(el).backgroundImage)) {
      named.add(path); out.push({path, replaced: true, name, value, later: [laterName, laterValue]}); } };
  for (const el of deepAll("[style]")) {
    dropped(el.getAttribute("style")).forEach(d => report(el, d));
    replaced(el.getAttribute("style")).forEach(d => lost(el, d));
  }
  const sheets = deepAll("style").map(s => [s.textContent, s.getRootNode()]);
  for (const link of document.querySelectorAll('link[rel~="stylesheet"][href]'))
    sheets.push([await fetch(link.href).then(r => r.ok ? r.text() : "").catch(() => ""), document]);
  for (const [text, root] of sheets) for (const [selector, body] of rules(text)) {
    const bad = dropped(body), gone = replaced(body);
    if (!(bad.length || gone.length) || selector.startsWith("@")) continue;
    let els = [];
    try { els = root.querySelectorAll(selector); } catch (e) { continue; }
    for (const el of els) { bad.forEach(d => report(el, d)); gone.forEach(d => lost(el, d)); }
  }
  return out;
}