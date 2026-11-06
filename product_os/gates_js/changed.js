
  const {seen, counts, texts} = window.__d2bWatch; seen.disconnect();
  const moving = outermost([...counts].filter(([el, n]) => n >= CHANGES && shown(el)).map(([el]) => el));
  const known = [...moving, ...named.map(find).filter(Boolean)];
  const near = (el, els) => els.some(o => o && (o.contains(el) || el.contains(o)));
  const pixels = [];
  for (const [x, y, w, h] of boxes) {
    const el = document.elementFromPoint(x + w / 2, y + h / 2);
    if (!el || near(el, known) || near(el, [...texts]) || near(el, pixels.map(p => p.el))) continue;
    pixels.push({el, box: [w, h]});
  }
  return {changing: moving.map(el => ({path: pathOf(el), changes: counts.get(el)})),
          pixels: pixels.map(p => ({path: pathOf(p.el), box: p.box}))};
}