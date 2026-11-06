
  const r = deepActive().getBoundingClientRect();
  return r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight && r.width > 0 && r.height > 0;
}