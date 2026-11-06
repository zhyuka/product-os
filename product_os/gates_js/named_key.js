  // The key the page's own text says moves focus on, as in "Press Ctrl+M to leave the editor",
  // in the form Playwright presses it, or null.
  const said = (document.body.innerText || "").match(new RegExp(
    "\\b(?:press|use|hit)\\s+((?:(?:ctrl|control|alt|option|shift|cmd|command|meta)\\s*\\+\\s*)*"
    + "(?:esc(?:ape)?|f\\d{1,2}|tab|enter|[a-z0-9]))\\b[^.\\n]{0,40}?\\b(?:exit|leave|close|escape|get out|"
    + "move (?:focus )?(?:out|on|away)|release)", "i"));
  if (!said) return null;
  const NAMES = {ctrl: "Control", control: "Control", alt: "Alt", option: "Alt", shift: "Shift", cmd: "Meta",
                 command: "Meta", meta: "Meta", esc: "Escape", escape: "Escape", tab: "Tab", enter: "Enter"};
  return said[1].split(/\s*\+\s*/).map(k => NAMES[k.toLowerCase()]
    || (/^f\d+$/i.test(k) ? k.toUpperCase() : k.toLowerCase())).join("+");
}
