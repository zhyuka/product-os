  return paths.filter(p => { for (let e = find(p); e; e = up(e)) if (e.getAttribute("aria-hidden") === "true") return true;
    return false; });
}
