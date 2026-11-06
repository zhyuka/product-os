
  const kept = [[document.scrollingElement, scrollY, scrollX]];
  for (let e = find(path); e; e = up(e)) kept.push([e, e.scrollTop, e.scrollLeft]);
  window.__d2bScroll = kept;
}