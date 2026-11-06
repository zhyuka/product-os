
  return deepAll(FOCUSABLE).filter(el => !blocked(el) && el.tabIndex >= 0
    && !el.checkVisibility({visibilityProperty: true})).map(el => {
      let box = up(el);
      while (box && box !== document.body && !shown(box)) box = up(box);
      return {path: pathOf(el), box: box && box !== document.body ? pathOf(box) : null};
    });
}