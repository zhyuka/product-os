
  const width = document.documentElement.clientWidth;
  const cut = [...document.body.querySelectorAll("*")].filter(el => {
    const r = el.getBoundingClientRect();
    if (!(r.left < width && r.right > width + 1 && shown(el))) return false;
    for (let c = el.parentElement; c && c !== document.body; c = c.parentElement)
      if (getComputedStyle(c).overflowX !== "visible") return false;  // it scrolls or clips inside its own box
    return true;
  });
  return {width, scrollWidth: document.documentElement.scrollWidth,
          cut: outermost(cut).map(el => ({path: pathOf(el), right: Math.round(el.getBoundingClientRect().right)}))};
}