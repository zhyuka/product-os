
  return animations().filter(a => a.playState === "running").map(a => {
    const t = a.effect.getComputedTiming();
    const left = t.endTime === Infinity ? Infinity : t.endTime - (a.currentTime || 0);
    return {path: pathOf(hostOf(a.effect.target)), name: a.animationName || a.transitionProperty || a.id || "animation",
            forever: t.iterations === Infinity, left};
  }).filter(a => a.forever || a.left > limit).map(a => ({...a, left: a.left === Infinity ? null : Math.round(a.left)}));
}