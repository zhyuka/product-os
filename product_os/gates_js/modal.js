
  return document.querySelectorAll("[inert]").length + document.querySelectorAll("dialog:modal").length
    + deepAll('[aria-modal="true"]').filter(shown).length;
}