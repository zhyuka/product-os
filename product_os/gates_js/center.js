
  const el = find(path);
  el.scrollIntoView({block: "center", inline: "center"});
  const r = el.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
}