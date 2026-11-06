() => { for (const [e, top, left] of window.__d2bScroll || [])
  if (e.scrollTop !== top || e.scrollLeft !== left) { e.scrollTop = top; e.scrollLeft = left; } }