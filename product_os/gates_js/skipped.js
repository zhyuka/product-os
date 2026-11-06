  const CONTROLS = 'a[href], button, input:not([type="hidden"]), select, textarea, summary';
  return deepAll(CONTROLS).filter(el => el.tabIndex < 0 && !blocked(el)
    && el.getAttribute("aria-disabled") !== "true" && !roving(el) && shown(el) && !clippedAway(el))
    .map(el => ({path: pathOf(el), href: hrefOf(el)}));
}
