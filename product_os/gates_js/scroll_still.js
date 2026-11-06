
  // Waits, up to limit ms, until the element at path, or with no path the one with focus, has
  // held still for 3 frames: where it is, how the page and every box around it are scrolled, and
  // how see-through each of them is. A smooth scroll can still be bringing it into view, and a
  // carousel can be sliding it in and fading it up.
  const target = () => path ? find(path) : deepActive();
  const at = () => { const out = [scrollX, scrollY], el = target();
    if (!el) return "";
    const r = el.getBoundingClientRect();
    out.push(Math.round(r.x), Math.round(r.y));
    for (let e = el; e; e = up(e)) out.push(e.scrollLeft, e.scrollTop, getComputedStyle(e).opacity);
    return out.join(","); };
  const frame = () => new Promise(done => requestAnimationFrame(done));
  const end = performance.now() + limit;
  let last = at(), still = 0;
  while (still < 3 && performance.now() < end) {
    await frame();
    const now = at();
    still = now === last ? still + 1 : 0;
    last = now;
  }
}
