  // Which of a widget's options and boxes are picked, which a click can change with no change to
  // any attribute.
  const box = find(path);
  return box ? [...box.querySelectorAll("option, input")].map(i => i.selected || i.checked ? 1 : 0).join("") : null;
}
