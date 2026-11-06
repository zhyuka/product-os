
  const a = deepActive();
  return a && a !== document.body && a !== document.documentElement ? pathOf(a) : null;
}