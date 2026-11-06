  // The paths of the elements the page changed since changes_start or the last call, and that
  // are still on the page and still changed: an attribute or a text not back to what it was, or
  // children not the same as those taken out. A change that removed an element is a change to
  // the box it was in.
  if (!window.__d2bWatch) return [];
  window.__d2bNote(window.__d2bWatch.takeRecords());
  const out = new Set(), same = (a, b) => a.slice().sort().join("\u0000") === b.slice().sort().join("\u0000");
  for (const [el, e] of window.__d2bChanged) {
    if (!el.isConnected || el.nodeType !== 1) continue;
    if ([...e.attrs].some(([name, old]) => el.getAttribute(name) !== old) || !same(e.added, e.removed))
      out.add(pathOf(el));
  }
  for (const [text, old] of window.__d2bTexts)
    if (text.isConnected && text.data !== old && text.parentElement) out.add(pathOf(text.parentElement));
  window.__d2bChanged = new Map();
  window.__d2bTexts = new Map();
  return [...out];
}
