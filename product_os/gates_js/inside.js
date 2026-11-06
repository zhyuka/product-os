  const b = find(box);
  return b ? paths.filter(p => { const el = find(p); return el && b.contains(el); }) : [];
}
