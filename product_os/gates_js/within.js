  // An element Tab can move on inside while the page's focus stays on it: a frame, through its
  // own links, and a date or time field, through its day, month, year or hour. For a frame the
  // page can read, where inside it focus is, as its place among the frame's elements.
  const el = deepActive();
  if (el && el.localName === "iframe") {
    let at = null;
    try {
      const doc = el.contentDocument, inner = doc && doc.activeElement;
      if (inner && inner !== doc.body) at = [...doc.querySelectorAll("*")].indexOf(inner);
    } catch (e) {}  // a frame from another site can't be read
    return {kind: "frame", at};
  }
  if (el && el.localName === "input" && /^(date|time|datetime-local|month|week)$/.test(el.type))
    return {kind: "field", at: null};
  return {kind: null, at: null};
}
