
  const ITEMS = '[role="tab"], [role^="menuitem"], [role="option"], [role="radio"], [role="treeitem"], [role="gridcell"], [role="row"], button, a[href], input, option';
  const LISTBOX = 'select[multiple], select[size]:not([size="0"]):not([size="1"])';
  const found = [];
  for (const stop of stops) { const el = find(stop);
    const box = el && (el.matches(LISTBOX) ? el : el.closest(ROVING));
    if (!box || found.some(f => f.box === box)) continue;
    const items = [...box.querySelectorAll(ITEMS)].filter(i => i !== box && shown(i));
    const now = box.localName === "select" ? box.selectedIndex : items.findIndex(i => i === el || i.contains(el));
    const next = items[now + 1] || items[now - 1];
    if (items.length > 1 && next) found.push({box, path: pathOf(box), stop, item: pathOf(next),
                                              text: (next.innerText || next.textContent || "").trim().slice(0, 40)});
  }
  return found.map(({box, ...rest}) => rest);
}