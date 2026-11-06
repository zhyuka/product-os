
  const load = s => new Promise(done => { const i = new Image(); i.onload = () => done(i);
    i.onerror = () => done(null); i.src = "data:image/png;base64," + s; });
  const [x, y] = await Promise.all([load(a), load(b)]);
  if (!x || !y) return null;
  // Pictures of different sizes are -1, or with crop, compared where both have pixels, from the
  // top left: an element that focus widens keeps its left edge.
  if (!crop && (x.width !== y.width || x.height !== y.height)) return -1;
  const c = document.createElement("canvas");
  c.width = Math.min(x.width, y.width); c.height = Math.min(x.height, y.height);
  const g = c.getContext("2d", {willReadFrequently: true});
  g.drawImage(x, 0, 0); const p = g.getImageData(0, 0, c.width, c.height).data;
  g.clearRect(0, 0, c.width, c.height);
  g.drawImage(y, 0, 0); const q = g.getImageData(0, 0, c.width, c.height).data;
  const off = i => Math.max(Math.abs(p[i] - q[i]), Math.abs(p[i + 1] - q[i + 1]), Math.abs(p[i + 2] - q[i + 2])) > cut;
