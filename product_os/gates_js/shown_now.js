
  return paths.filter(p => { const el = find(p); return el && focusable(el); });
}