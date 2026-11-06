
  return paths.filter(p => { const el = find(p); return el && !el.readOnly
    && (el.matches('input:is(:not([type]), [type="text"], [type="search"], [type="email"], [type="url"], [type="tel"])')
        || el.getAttribute("role") === "combobox"); });
}