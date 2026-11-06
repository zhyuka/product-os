
  const BUTTON = 'button, input[type="button"], input[type="submit"], input[type="reset"], input[type="image"], summary, '
    + 'input[readonly], [role="combobox"]';  // a picker a click opens: a date field, say
  const NATIVE = 'a[href], area[href], input, select, textarea, iframe';
  const ROLES = ["button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "option"];
  return paths.filter(p => { const el = find(p);
    return el && (el.matches(BUTTON) || (!el.matches(NATIVE) && (listens(el, ...MOUSE)
      || getComputedStyle(el).cursor === "pointer" || ROLES.includes(el.getAttribute("role"))))); });
}