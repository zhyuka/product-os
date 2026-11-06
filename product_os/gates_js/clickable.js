
  const ROLES = ["button", "link", "tab", "menuitem", "checkbox", "radio", "switch", "option"];
  // A mouse can drag one too: a list item that drag and drop reorders, say.
  const draggable = el => el.getAttribute("draggable") === "true" || /^(grab|move)$/.test(getComputedStyle(el).cursor);
  const clickable = el => getComputedStyle(el).cursor === "pointer" || listens(el, ...MOUSE)
    || ROLES.includes(el.getAttribute("role")) || draggable(el);
  const reachable = el => {
    for (let e = el; e; e = up(e)) if (focusable(e)) return true;
    const label = el.closest("label");  // a click on a label works its control
    if (label && label.control && focusable(label.control)) return true;
    return deepAll(FOCUSABLE, el).some(focusable);
  };
  const label = el => el.localName === "label" && (el.control || el.querySelector("input, select, textarea"));
  const found = deepAll("*", document.body).filter(el => shown(el) && clickable(el)
    && !blocked(el) && el.getAttribute("aria-disabled") !== "true" && !label(el) && !reachable(el)
    && !roving(el) && !clippedAway(el));
  return outermost(found).map(el => ({path: pathOf(el), href: hrefOf(el), text: (el.innerText || "").trim().slice(0, 40),
                                      does: draggable(el) && getComputedStyle(el).cursor !== "pointer" ? "drag"
                                        : listens(el, "dblclick") && !listens(el, "click") ? "double-click" : "click"}));
}