
  // The boxes around the element, nearest first, short of the body and at most 6, each with its
  // style, so a style that focus inside one of them changes, as :focus-within does, is seen.
  const el = find(path), out = [];
  for (let e = el && up(el); e && e !== document.body && e !== document.documentElement && out.length < 6; e = up(e)) {
    const s = getComputedStyle(e);
    out.push({path: pathOf(e), style: props.map(p => s.getPropertyValue(p)).join("|")});
  }
  return out;
}
