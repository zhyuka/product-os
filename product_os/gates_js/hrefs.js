  return paths.map(p => { const el = find(p); return el && hrefOf(el); }).filter(Boolean);
}
