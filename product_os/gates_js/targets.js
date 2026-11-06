
  return deepAll(FOCUSABLE).filter(focusable)
    .map(el => ({path: pathOf(el), proxy: pathOf(proxyOf(el)),
                 group: el.type === "radio" && el.name ? pathOf(el.form || document.body) + "|" + el.name : null}));
}