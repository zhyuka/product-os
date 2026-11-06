
  // Makes the element see-through, or with through false puts back what it was.
  const el = find(path);
  if (!el) return;
  if (through) {
    el.__d2bOpacity = [el.style.getPropertyValue("opacity"), el.style.getPropertyPriority("opacity")];
    el.style.setProperty("opacity", "0", "important");
  } else if (el.__d2bOpacity) {
    el.style.setProperty("opacity", ...el.__d2bOpacity);
    delete el.__d2bOpacity;
  }
}
