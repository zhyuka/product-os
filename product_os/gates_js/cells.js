
  const cols = Math.ceil(c.width / cell), counts = new Map();
  for (let i = 0; i < p.length; i += 4) if (off(i)) {
    const px = (i / 4) % c.width, py = Math.floor(i / 4 / c.width);
    const k = Math.floor(py / cell) * cols + Math.floor(px / cell);
    counts.set(k, (counts.get(k) || 0) + 1);
  }
  return {cols, cells: [...counts].filter(([, n]) => n >= least).map(([k]) => k)};
}