() => {
  const counts = new Map(), texts = new Set();
  const seen = new MutationObserver(list => { for (const m of list) {
    if (m.type === "attributes") counts.set(m.target, (counts.get(m.target) || 0) + 1);
    else texts.add(m.type === "characterData" ? m.target.parentElement : m.target); } });
  seen.observe(document.documentElement, {attributes: true, attributeFilter: ["style", "class"], subtree: true,
                                          characterData: true, childList: true});
  window.__d2bWatch = {seen, counts, texts};
}