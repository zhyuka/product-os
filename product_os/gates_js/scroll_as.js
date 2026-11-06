
  // Scrolls the window and the boxes SCROLLS listed back to where it found them, at once even
  // where the page scrolls smoothly, keeping where they were for PUT_SCROLL_BACK.
  const kept = [];
  for (const [path, top, left] of scrolls) {
    const e = path === null ? document.scrollingElement : find(path);
    if (!e) continue;
    kept.push([e, e.scrollTop, e.scrollLeft]);
    e.scrollTo({top, left, behavior: "instant"});
  }
  window.__d2bScroll = kept;
}
