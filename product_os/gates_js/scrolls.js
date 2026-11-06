
  // Where the window and each box around the element at path are scrolled to: the window as null.
  const out = [[null, scrollY, scrollX]], el = find(path);
  for (let e = el && up(el); e; e = up(e))
    if (e !== document.scrollingElement && (e.scrollTop || e.scrollLeft)) out.push([pathOf(e), e.scrollTop, e.scrollLeft]);
  return out;
}
