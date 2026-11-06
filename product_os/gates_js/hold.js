
// As Playwright's screenshot holds them, so what is measured is what is pictured: one that
// ends is put at its end, and one that loops is taken off until RELEASE plays it again. One
// the page paused, or one that has finished, stays as it is.
window.__d2bHeld = [];
animations().forEach(a => {
  if (a.playState !== "running") return;
  if (isFinite(a.effect.getComputedTiming().endTime)) { try { a.finish(); } catch (e) {} return; }
  window.__d2bHeld.push(a); a.cancel(); }) }
