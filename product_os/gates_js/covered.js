
  const el = find(path);
  if (!el) return null;
  const root = el.getRootNode();
  // Each line a wrapped link takes is a box of its own, so no point lands between its lines.
  const lines = [...el.getClientRects()].filter(r => r.width > 1 && r.height > 1);
  let by = null;
  for (const r of lines.length ? lines : [el.getBoundingClientRect()])
    for (const [fx, fy] of [[.5, .5], [.2, .2], [.8, .2], [.2, .8], [.8, .8]]) {
      const x = r.left + r.width * fx, y = r.top + r.height * fy;
      if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return null;
      const hit = root.elementFromPoint(x, y);
      if (!hit || el.contains(hit) || hit.contains(el)) return null;
      by = by || hit;
    }
  return pathOf(by);
}
