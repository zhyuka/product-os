
  const CONTROLS = 'button, input:not([type="hidden"]), select, textarea, [role="button"]';
  return deepAll(CONTROLS).filter(el => shown(el) && (el.matches(":disabled") || el.getAttribute("aria-disabled") === "true"))
    .map(pathOf);
}