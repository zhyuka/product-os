  // Relative luminance and contrast ratio, as WCAG defines them.
  const lum = v => { const ch = c => { c /= 255; return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; };
    return .2126 * ch(v >> 16 & 255) + .7152 * ch(v >> 8 & 255) + .0722 * ch(v & 255); };
  const ratio = (a, b) => { a = lum(a); b = lum(b); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); };
  const rgb = (d, k) => d[k * 4] << 16 | d[k * 4 + 1] << 8 | d[k * 4 + 2];
  const w = c.width, h = c.height, changed = new Uint8Array(w * h);
  let n = 0;
  for (let k = 0; k < w * h; k++) if (off(k * 4)) { changed[k] = 1; n++; }
  // The element's box in the picture, [x, y, width, height], splits what changed into a part
  // outside it, such as a ring, and a part inside it, such as a border or a fill. As WCAG 1.4.11's
  // Understanding page has it, each part is held against every colour touching it on its own
  // side: a ring outside against the background, a border inside against the fill.
  const inside = k => { if (!box) return 0; const x = k % w, y = (k - x) / w;
    return +(x >= box[0] && x < box[0] + box[2] && y >= box[1] && y < box[1] + box[3]); };
  const parts = [0, 1].map(() => ({n: 0, colours: new Map(), beside: new Map()}));
  const add = (map, key) => map.set(key, (map.get(key) || 0) + 1);
  const touch = (part, colour, other) => {
    if (!part.beside.has(colour)) part.beside.set(colour, new Map());
    add(part.beside.get(colour), other);
  };
  const shifts = [];
  for (let k = 0; k < w * h; k++) if (changed[k]) {
    const x = k % w, y = (k - x) / w, side = inside(k), part = parts[side], now = rgb(q, k);
    part.n++;
    add(part.colours, now);
    shifts.push(ratio(now, rgb(p, k)));
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const nx = x + dx, ny = y + dy, j = ny * w + nx;
      if (nx >= 0 && ny >= 0 && nx < w && ny < h && !changed[j] && inside(j) === side) touch(part, now, rgb(q, j));
    }
  }
  // A part can be drawn in bands, as the browser's own ring is, blue with white beside it: each
  // colour that holds a fifth of the part is a band, held against the colours touching it that
  // make up a tenth of what does, so a speck of anti-aliasing or a letter's edge doesn't decide.
  // The part reaches what its best band reaches.
  const score = part => {
    let best = null;
    for (const [colour, count] of part.colours) {
      const beside = part.beside.get(colour);
      if (count < part.n / 5 || !beside) continue;
      const total = [...beside.values()].reduce((a, b) => a + b, 0);
      const worst = Math.min(...[...beside].filter(([, m]) => m >= total / 10).map(([v]) => ratio(colour, v)));
      best = best === null ? worst : Math.max(best, worst);
    }
    return best;
  };
  shifts.sort((a, b) => a - b);
  // Which sides of the box focus shows on: a side counts when changes run along half of it,
  // within 8 px outside it or 10 px inside, where an inset ring is drawn.
  let sides = null;
  if (box) {
    const [bx, by, bw, bh] = box, along = [new Set(), new Set(), new Set(), new Set()];
    for (let k = 0; k < w * h; k++) if (changed[k]) {
      const x = k % w, y = (k - x) / w, across = x >= bx && x < bx + bw, down = y >= by && y < by + bh;
      if (across && y >= by - 8 && y < by + 10) along[0].add(x);
      if (across && y >= by + bh - 10 && y < by + bh + 8) along[1].add(x);
      if (down && x >= bx - 8 && x < bx + 10) along[2].add(y);
      if (down && x >= bx + bw - 10 && x < bx + bw + 8) along[3].add(y);
    }
    sides = along.filter((s, i) => s.size >= (i < 2 ? bw : bh) / 2).length;
  }
  return {changed: n, outside: score(parts[0]), inside: score(parts[1]), shift: n ? shifts[n >> 1] : 1, sides};
}
