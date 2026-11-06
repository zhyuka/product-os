
  return paths.filter(p => { const el = find(p);
    return el && (el.matches(":disabled") || el.getAttribute("aria-disabled") === "true"); });
}