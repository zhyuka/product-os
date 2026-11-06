  // Starts noting what the page changes, in the page and in every open shadow root: each
  // attribute's value before its first change, each text's, and the children taken out and put
  // in, so that a write that leaves things as they were, as setting hidden on what's hidden does,
  // isn't a change. A class on <html> or <body>, which some pages set on any key to style
  // keyboard focus, isn't a change either.
  window.__d2bChanged = new Map();
  window.__d2bTexts = new Map();
  if (window.__d2bWatch) return;
  const html = n => n.nodeType === 1 ? n.outerHTML : n.textContent;
  const entry = el => { let e = window.__d2bChanged.get(el);
    if (!e) window.__d2bChanged.set(el, e = {attrs: new Map(), added: [], removed: []});
    return e; };
  window.__d2bNote = records => { for (const r of records) {
    if (r.type === "characterData") {
      if (!window.__d2bTexts.has(r.target)) window.__d2bTexts.set(r.target, r.oldValue);
    } else if (r.type === "attributes") {
      if (r.target === document.documentElement || r.target === document.body) continue;
      const e = entry(r.target);
      if (!e.attrs.has(r.attributeName)) e.attrs.set(r.attributeName, r.oldValue);
    } else {
      const box = r.target instanceof ShadowRoot ? r.target.host : r.target;  // a shadow root's children
      if (box.nodeType !== 1) continue;
      const e = entry(box);
      for (const n of r.addedNodes) e.added.push(html(n));
      for (const n of r.removedNodes) e.removed.push(html(n));
    }
  } };
  window.__d2bWatch = new MutationObserver(window.__d2bNote);
  const options = {subtree: true, childList: true, attributes: true, characterData: true,
                   attributeOldValue: true, characterDataOldValue: true};
  window.__d2bWatch.observe(document, options);
  for (const host of deepAll("*")) if (host.shadowRoot) window.__d2bWatch.observe(host.shadowRoot, options);
}
