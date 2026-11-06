
  return deepAll("*", document.body).filter(el => shown(el) && (getComputedStyle(el).cursor === "pointer"
    || el.hasAttribute("onclick") || ["option", "menuitem"].includes(el.getAttribute("role")))).map(pathOf);
}