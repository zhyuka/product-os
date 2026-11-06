
  const rules = list => [...list].flatMap(r => r.selectorText ? [r]  // a style rule has cssRules too, for nesting
    : r.cssRules && (!r.media || matchMedia(r.media.mediaText).matches) ? rules(r.cssRules) : []);
  const sheets = root => [...root.styleSheets, ...(root.adoptedStyleSheets || [])]
    .flatMap(s => { try { return rules(s.cssRules); } catch (e) { return []; } });
  return deepAll("*", document.body).flatMap(el => {
    const s = getComputedStyle(el), src = (s.backgroundImage.match(/url\(["']?([^"')]+)/) || [])[1];
    if (!src || !["inline", "contents"].includes(s.display) || el.getClientRects().length > 1) return [];
    const set = [el.style, ...sheets(el.getRootNode()).filter(r => { try { return el.matches(r.selectorText); }
                                                                     catch (e) { return false; } }).map(r => r.style)];
    const sized = set.map(st => [st.width, st.height]).find(([w, h]) => parseFloat(w) > 0 || parseFloat(h) > 0);
    const r = el.getBoundingClientRect();  // under half the size set in either direction
    if (!sized || (r.width >= parseFloat(sized[0] || 0) / 2 && r.height >= parseFloat(sized[1] || 0) / 2)) return [];
    return [{path: pathOf(el), src: new URL(src, document.baseURI).href, display: s.display,
             set: sized.map(v => v || "auto"), drawn: [Math.round(r.width), Math.round(r.height)]}];
  });
}