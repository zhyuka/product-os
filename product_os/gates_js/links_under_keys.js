
  const keyed = e => listens(e, "keydown", "keypress", "keyup");
  return paths.filter(p => { const el = find(p);
    if (!el || !el.matches("a[href], area[href]")) return false;
    for (let e = el; e && e !== document.body && e !== document.documentElement; e = up(e)) if (keyed(e)) return true;
    return false; });
}