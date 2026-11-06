
// An element inside a component's open shadow root is named by its host's path, " >>> ", and
// its path in the shadow root. find() reads such a path back, and so does Playwright once
// " >>> " is " >> ". A path names one element: it is up to 4 steps long, and longer only until
// nothing else matches, since the same card markup repeats down a page. An id counts only
// where the page has it once.
const pathOf = el => {
  if (!el || el.nodeType !== 1) return "";
  const root = el.getRootNode(), scope = root instanceof ShadowRoot ? root : document;
  const one = selector => { try { return scope.querySelectorAll(selector).length === 1; } catch (e) { return false; } };
  const parts = [];
  for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
    const id = e.id && "#" + CSS.escape(e.id);
    if (id && one(id)) { parts.unshift(id); break; }
    let part = e.localName;
    const same = e.parentElement ? [...e.parentElement.children].filter(c => c.localName === e.localName) : [];
    if (same.length > 1) part += `:nth-of-type(${same.indexOf(e) + 1})`;
    parts.unshift(part);
    if (e === document.body || (parts.length >= 4 && one(parts.join(" > ")))) break;
  }
  return (root instanceof ShadowRoot ? pathOf(root.host) + " >>> " : "") + parts.join(" > ");
};
const find = path => { let root = document, el = null;
  for (const part of path.split(" >>> ")) { el = root && root.querySelector(part); if (!el) return null; root = el.shadowRoot; }
  return el; };
// Every element under root that matches, in open shadow roots too.
const deepAll = (selector, root = document) => {
  const out = [], roots = root.shadowRoot ? [root, root.shadowRoot] : [root];
  for (const r of roots) { out.push(...r.querySelectorAll(selector));
    for (const el of r.querySelectorAll("*")) if (el.shadowRoot) out.push(...deepAll(selector, el.shadowRoot)); }
  return out;
};
// The element around this one, past a shadow root's edge to its host.
const up = el => el.parentElement || (el.getRootNode() instanceof ShadowRoot ? el.getRootNode().host : null);
// Whether the element has a listener for any of the events, added in a script or as an attribute.
const listens = (el, ...types) => types.some(t => (el.__d2bOn && el.__d2bOn.has(t)) || el.hasAttribute("on" + t));
const MOUSE = ["click", "dblclick", "mousedown", "mouseup", "pointerdown", "pointerup"];
const deepActive = () => { let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  return a; };
const shown = el => {
  const r = el.getBoundingClientRect();
  return r.width > 1 && r.height > 1 && el.checkVisibility({opacityProperty: true, visibilityProperty: true});
};
const FOCUSABLE = 'a[href], area[href], button, input:not([type="hidden"]), select, textarea, summary, iframe, [tabindex], [contenteditable]:not([contenteditable="false"])';
// Whether the element can't take focus or a click, whatever its tabindex: disabled, by itself or
// by a disabled fieldset, as :disabled has it; inside inert; or outside an open modal dialog,
// which makes the rest of the page inert, or which aria-modal says the page waits behind. The
// open dialog is looked for once per script.
let openModal;
const blocked = el => {
  if (el.matches(":disabled")) return true;
  for (let e = el; e; e = up(e)) if (e.hasAttribute("inert")) return true;
  if (openModal === undefined)
    openModal = deepAll("dialog:modal")[0] || deepAll('[aria-modal="true"]').find(shown) || null;
  const modal = openModal;
  if (!modal) return false;
  for (let e = el; e; e = up(e)) if (e === modal) return false;
  return true;
};
// In the Tab order: an element with opacity 0, such as the real input under a custom
// checkbox, still takes focus, so only display and visibility count here.
const focusable = el => { const r = el.getBoundingClientRect();
  return el.matches(FOCUSABLE) && !blocked(el) && el.tabIndex >= 0 && r.width > 0 && r.height > 0
    && el.checkVisibility({visibilityProperty: true}); };
// What shows that an element has focus: itself, or for one that can't be seen, its label or
// the nearest box around it that can.
const proxyOf = el => {
  if (shown(el)) return el;
  if (el.labels && el.labels.length && shown(el.labels[0])) return el.labels[0];
  for (let e = up(el); e && e !== document.body; e = up(e)) if (shown(e)) return e;
  return el;
};
const outermost = els => els.filter(el => !els.some(other => other !== el && other.contains(el)));
// Whether a box around the element that hides what overflows it, as a carousel's frame does,
// hides all of the element, so that neither a mouse nor Tab can get to it as the page is. Only
// the page itself, and a box around a fixed element, don't count.
const clippedAway = el => { const r = el.getBoundingClientRect(), hides = v => v === "hidden" || v === "clip";
  let fixed = getComputedStyle(el).position === "fixed";
  for (let e = up(el); e && e !== document.documentElement && !fixed; e = up(e)) {
    const s = getComputedStyle(e), b = e.getBoundingClientRect();
    if (hides(s.overflowX) && (r.right <= b.left || r.left >= b.right)) return true;
    if (hides(s.overflowY) && (r.bottom <= b.top || r.top >= b.bottom)) return true;
    fixed = s.position === "fixed";
  }
  return false; };
// Where the link at or around the element goes, as the browser resolves it.
const hrefOf = el => { const a = el.closest("a[href], area[href]");
  return a && (a instanceof HTMLAnchorElement || a instanceof HTMLAreaElement) ? a.href : null; };
// A widget that moves focus with the arrow keys, such as a tab list, a menu or a toolbar. Only
// its current item is in the Tab order, so the rest rightly have tabindex=-1.
const ROVING = '[role="tablist"], [role="menu"], [role="menubar"], [role="listbox"], [role="radiogroup"], [role="toolbar"], [role="grid"], [role="tree"], [role="treegrid"]';
const roving = el => { const box = el.closest(ROVING);
  return !!box && (focusable(box) || [...box.querySelectorAll(FOCUSABLE)].some(focusable)); };
