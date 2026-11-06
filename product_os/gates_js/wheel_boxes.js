
  const inside = stops.map(find).filter(Boolean);
  return deepAll("*", document.body).filter(el => { const s = getComputedStyle(el);
    return shown(el) && listens(el, "wheel", "mousewheel") && /hidden|clip/.test(s.overflowX + s.overflowY)
      && (el.scrollHeight > el.clientHeight + 4 || el.scrollWidth > el.clientWidth + 4)
      && !inside.some(t => el === t || el.contains(t)); }).map(pathOf);
}