
  const ROLES = ["slider", "scrollbar", "separator", "spinbutton"];
  return paths.filter(p => { const el = find(p);
    return el && (ROLES.includes(el.getAttribute("role")) || /resize|grab|move/.test(getComputedStyle(el).cursor)); });
}