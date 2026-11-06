
  const ms = v => { if (!v) return null; const n = parseFloat(v);
    return /ms$/.test(v) ? n : /min$/.test(v) ? n * 60000 : /h$/.test(v) ? n * 3600000 : n * 1000; };
  return [...document.querySelectorAll("animate, animateTransform, animateMotion, animateColor, set")].filter(a => {
    const svg = a.ownerSVGElement;
    if (!svg || !shown(svg) || svg.animationsPaused()) return false;
    const count = a.getAttribute("repeatCount"), total = a.getAttribute("repeatDur");
    if (count === "indefinite" || total === "indefinite") return true;
    const once = ms(a.getAttribute("dur")) || 0;
    return (ms(total) || once * (parseFloat(count) || 1)) > limit;
  }).map(a => ({path: pathOf(a.ownerSVGElement), name: `<${a.localName}>`}));
}