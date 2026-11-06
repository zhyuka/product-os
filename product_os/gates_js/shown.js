
  // Whether the element at path shows as proxyOf has it: bigger than a pixel, and neither
  // see-through nor hidden.
  const el = find(path);
  return !!el && shown(el);
}
