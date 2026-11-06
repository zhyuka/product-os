"""product-os gates: a page that a keyboard can use, that shows focus, fits its width, has
sharp images and holds still for reduced motion passes every gate, and each planted page that
breaks one fails that gate and no other.

Skipped without Playwright and its Chromium.
"""
import ast
import base64
import io
import json
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from product_os import design, exercise, gates
from product_os.cli import main

GOOD = """<!doctype html><meta name=viewport content="width=device-width">
<style>
  body { margin: 0; font: 16px sans-serif; }
  main { padding: 16px; max-width: 100%; box-sizing: border-box; }
  a:focus-visible, button:focus-visible { outline: 3px solid #05f; outline-offset: 2px; }
  .card { cursor: pointer; padding: 8px; border: 1px solid #ccc; }
  img { width: 300px; height: 150px; display: block; max-width: 100%; }
  .spin { width: 20px; height: 20px; background: #05f; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
</style>
<main>
  <nav><a href="#home">Home</a> <a href="#docs">Docs</a></nav>
  <button>Get started</button>
  <div class=card onclick="location.hash = 'case'"><a href="#case">Read the case study</a></div>
  <img src="big.png" alt="">
  <div class=hero style="width: 300px; height: 150px; max-width: 100%; background: url(big.png) center / cover"></div>
  <div role=tablist><button role=tab aria-selected=true>One</button><button role=tab tabindex=-1>Two</button></div>
  <div class=spin></div>
</main>
"""

# A component with a button of its own, in its shadow root, that shows focus.
COMPONENT = ("<script>customElements.define('x-copy', class extends HTMLElement { connectedCallback() { "
             "this.attachShadow({mode: 'open'}).innerHTML = '<style>button:focus-visible { outline: 3px solid "
             "#05f }</style><button>Copy</button>' } })</script>")

# A handle a drag moves, which sets --pos on its box. KEYS adds the arrow keys.
HANDLE = ("<div id=pane style='position: relative; width: 200px; height: 20px; background: #eee'><button id=knob "
          "aria-label=Compare style='position: absolute; left: var(--pos, 50%); width: 20px; height: 20px; cursor: "
          "ew-resize'></button></div><script>knob.onpointerdown = e => { knob.setPointerCapture(e.pointerId); "
          "knob.onpointermove = m => pane.style.setProperty('--pos', Math.round(m.clientX - pane.getBoundingClientRect()"
          ".left) + 'px') }; knob.onpointerup = () => { knob.onpointermove = null };</script>")
KEYS = ("<script>knob.onkeydown = e => { if (e.key === 'ArrowRight') pane.style.setProperty('--pos', '80%') }"
        "</script>")

# A field that suggests cities as you type, picked with the mouse. ARROWS adds the down arrow.
SUGGEST = ("<input id=city aria-label=City autocomplete=off><ul id=picks></ul><style>#picks li { cursor: pointer }"
           " input:focus-visible { outline: 3px solid #05f }</style><script>city.oninput = () => { picks.innerHTML = "
           "city.value ? '<li>Seoul</li><li>Sydney</li>' : '' }; picks.onmousedown = e => { city.value = "
           "e.target.textContent; picks.innerHTML = '' }</script>")
ARROWS = ("<script>city.addEventListener('keydown', e => { if (e.key === 'ArrowDown' && picks.firstChild) "
          "picks.firstChild.setAttribute('aria-selected', 'true') })</script>")

# A box that clips its notes and scrolls them on the wheel; {} takes what else is in it.
WHEEL = ("<div id=notes style='height: 40px; overflow: hidden'>{}<p>One</p><p>Two</p><p>Three</p><p>Four</p></div>"
         "<script>notes.addEventListener('wheel', e => {{ notes.scrollTop += e.deltaY; e.preventDefault() }}, "
         "{{passive: false}})</script>")
# A box of checkboxes that scrolls, with a bar stuck to its bottom; {} takes the box's own style.
STICKY = ("<div style='height: 90px; overflow-y: auto; {}'>" + "".join(
    f"<label style='display: block'><input type=checkbox> Box {n}</label>" for n in range(1, 7))
    + "<div style='position: sticky; bottom: 0; height: 40px; background: #fff'><button>Apply</button></div></div>"
    "<style>input:focus-visible {{ outline: 3px solid #05f }}</style>")
# A label that stands in for a hidden file field; {} takes the label's other attributes.
PICKER = ("<label class=attach for=brief tabindex=0 {}>Attach a brief</label><input type=file id=brief hidden>"
          "<style>.attach {{ cursor: pointer }} .attach:focus-visible {{ outline: 3px solid #05f }}</style>")
# Two tabs a click switches, moving the one Tab stop between them; {} takes more script.
TABS = ("<div role=tablist id=tabs><button role=tab id=t1 aria-selected=true>Plans</button><button role=tab id=t2 "
        "tabindex=-1 aria-selected=false>Pricing</button></div><p id=p1>Plans</p><p id=p2 hidden>Pricing</p><script>"
        "for (const t of [t1, t2]) t.addEventListener('click', () => {{ for (const u of [t1, t2]) {{ u.tabIndex = "
        "u === t ? 0 : -1; u.setAttribute('aria-selected', u === t) }} p1.hidden = t !== t1; p2.hidden = t !== t2 }});"
        " {}</script>")
# A list box of industries over a line of results; {} takes the script that fills the line.
LISTBOX = ("<select id=industry size=3 aria-label=Industry><option>Banking</option><option>Retail</option><option>"
           "Health</option></select><p id=results>All industries</p><style>select:focus-visible {{ outline: 3px "
           "solid #05f }}</style><script>{}</script>")
# A cookie banner that a cookie hides once it's accepted, and that thanks you with a link and a
# button, as most sites' do.
CONSENT = ("<div id=consent><p>We use cookies.</p><button id=accept>Accept</button></div><script>if (document.cookie"
           ".includes('ok=1')) consent.hidden = true; accept.onclick = () => { document.cookie = 'ok=1; path=/'; "
           "consent.innerHTML = '<p id=saved tabindex=-1>Saved. <a href=\"#settings\">Change your settings</a> <button "
           "onclick=\"consent.hidden = true\">Hide this</button></p>'; saved.focus() }</script>")
# The good page's focus ring and its card, for pages that change how focus shows.
RING = "a:focus-visible, button:focus-visible { outline: 3px solid #05f; outline-offset: 2px; }"
CARD = '<div class=card onclick="location.hash = \'case\'"><a href="#case">Read the case study</a></div>'
# A card that shows focus with a ring of its own, clear of what's around it; {} takes the colour.
FOCUS_WITHIN = CARD + ("<style>.card {{ margin: 16px 0 }} .card a {{ outline: none }} .card:focus-within {{ outline: "
                       "4px solid {} }}</style>")
# Links of three words each, several to a line, so some wrap onto the next.
WORDS = "the plans pricing a guide to every gate and what each one checks for you and why it fails".split()
WRAPPING = "<p>" + " ".join(f"<a href='#w{n}'>{' '.join(WORDS[n:n + 3])}</a>" for n in range(0, len(WORDS), 3)) * 3 + "</p>"
# A row of cards wider than a phone that scrolls smoothly, as a carousel's does.
ROW = ("<div class=row>" + "".join(f"<button>Card {n}</button>" for n in range(1, 7)) + "</div><style>.row { display: "
       "flex; gap: 16px; overflow-x: auto; scroll-behavior: smooth } .row button { flex: 0 0 260px; height: 80px }</style>")
# A logo drawn as the background of a span; {} takes more of its style.
LOGO = ("<span class=logo role=img aria-label=Logo></span><style>.logo {{ {} width: 96px; height: 32px; "
        "background: url(big.png) 0 0 / 96px 32px no-repeat }}</style>")
# A link that focus fills pale yellow, its edges off the pixel grid, as text often puts them;
# {} takes its text's colour.
OFF_GRID = ("<div class=spin></div><p style='margin: 0 0 0 40.8px'><a class=fill href='#fill' style='display: "
            "inline-block; width: 75.5px; padding: 12px 0; color: {}'>Support</a></p><style>.fill:focus-visible "
            "{{ outline: none; background: #fd3 }}</style>")
# A row of slides past the first that stay see-through until the row first scrolls, as a carousel
# shows them; {} takes more style.
SLIDES = ("<div class=spin></div><div class=slides>" + "".join(f"<div class=slide><a href='#s{n}'>Slide {n}</a></div>"
                                                               for n in range(1, 5))
          + "</div><style>.slides {{ display: flex; gap: 16px; overflow-x: auto }} .slide {{ flex: 0 0 340px; padding: "
            "24px; box-sizing: border-box; border: 1px solid #ccc }} .slide + .slide {{ opacity: 0 }} .seen .slide {{ "
            "opacity: 1 !important }} {}</style><script>document.querySelector('.slides').addEventListener('scroll', "
            "e => e.target.classList.add('seen'))</script>")
# A box a script changes over 600 ms once focus enters it, as a carousel slides and fades its
# slides; {} take the box's style, what's in it, and the style it sets to what t, 0 to 1, gives.
SCRIPTED = ("<div class=spin></div><div class=moves style='padding: 16px; {}'>{}</div><script>document.querySelector("
            "'.moves').addEventListener('focusin', e => {{ const box = e.currentTarget, start = performance.now(); "
            "requestAnimationFrame(function step(now) {{ const t = Math.min((now - start) / 600, 1); box.style.{} = {}; "
            "if (t < 1) requestAnimationFrame(step); }}); }})</script>")
# A div a click works, and Tab reaches; {} takes more of its attributes. And a clock that ticks.
DIV_BUTTON = ("<div role=button tabindex=0 id=go onclick=\"this.textContent = 'Started'\"{}>Go</div><style>"
              "[role=button]:focus-visible {{ outline: 3px solid #05f }}</style>")
CLOCK = "<p id=clock></p><script>setInterval(() => { clock.textContent = Date.now() }, 100)</script>"

# Each plant breaks one gate: its changes to GOOD, and the gate it has to fail.
PLANTED = {
    "a div for a button": ([("<button>Get started</button>",
                             "<div style='cursor: pointer' onclick=\"location.hash = 'go'\">Get started</div>")],
                           "keyboard"),
    "a field Tab can't leave": ([("<button>Get started</button>",
                                  "<input id=field><script>field.addEventListener('keydown', e => "
                                  "{ if (e.key === 'Tab') e.preventDefault(); })</script>")], "keyboard"),
    "no focus style": ([("a:focus-visible, button:focus-visible { outline: 3px solid #05f; "
                         "outline-offset: 2px; }", "*:focus { outline: none; }")], "focus"),
    "a block wider than a phone": ([("<div class=spin></div>",
                                     "<div class=spin></div><div style='width: 600px; height: 8px'></div>")],
                                   "overflow"),
    "a small image drawn large": ([('src="big.png"', 'src="small.png"')], "images"),
    "a missing image": ([('src="big.png"', 'src="gone.png"')], "images"),
    "a spinner that ignores reduced motion": ([("  @media (prefers-reduced-motion: reduce) "
                                                "{ .spin { animation: none; } }\n", "")], "motion"),
    "a button taken out of the Tab order": ([("<button>Get started</button>",
                                              '<button tabindex="-1">Get started</button>')], "keyboard"),
    "a skip link that stays off the screen": ([("<main>\n", '<a href="#docs" style="position: '
                                                "absolute; left: -9999px\">Skip to the docs</a>\n<main>\n")],
                                              "focus"),
    "a skip link that slides in pale": ([("<main>\n", "<a class=skip href='#docs'>Skip to the docs</a><style>.skip "
                                          "{ position: absolute; right: 8px; top: -60px } .skip:focus { top: 4px; "
                                          "outline: none; color: #bbb }</style>\n<main>\n")], "focus"),
    "a link off the pixel grid that focus fills pale behind pale text": ([("<div class=spin></div>",
                                                                          OFF_GRID.format("#bbb"))], "focus"),
    "slides a carousel shows on scrolling, with no focus style": ([("<div class=spin></div>", SLIDES.format(
        ".slide + .slide a:focus-visible { outline: none }"))], "focus"),
    "a link a script slides along with focus, with no focus style": ([("<div class=spin></div>", SCRIPTED.format(
        "", "<a href='#g' style='outline: none'>Slides along</a>", "transform", "`translateX(${120 * t}px)`"))], "focus"),
    "a small background image drawn large": ([("url(big.png) center / cover", "url(small.png) center / cover")],
                                             "images"),
    "a script that bobs a dot": ([("<div class=spin></div>", "<div class=spin></div><div id=bob style='width: "
                                   "8px; height: 8px; background: #05f'></div><script>(function bob_(t) { "
                                   "bob.style.transform = `translateY(${Math.sin(t / 200) * 4}px)`; "
                                   "requestAnimationFrame(bob_); })(0)</script>")], "motion"),
    "a menu only a hover opens": ([("<nav><a href=\"#home\">Home</a> <a href=\"#docs\">Docs</a></nav>",
                                    "<style>.more ul { display: none } .more:hover ul { display: block }</style>"
                                    "<nav><a href=\"#home\">Home</a> <a href=\"#docs\">Docs</a> <span class=more>"
                                    "More<ul><li><a href=\"#blog\">Blog</a></li></ul></span></nav>")], "keyboard"),
    # Where a pointer parked at (0, 0) would hover it open.
    "a menu only a hover opens, in the top left corner": ([(
        "<main>\n", "<style>.more ul { display: none } .more:hover ul { display: block }</style><span class=more "
        "style='position: absolute; top: 0; left: 0'>More<ul><li><a href='#blog'>Blog</a></li></ul></span>\n<main "
        "style='margin-top: 24px'>\n")], "keyboard"),
    "a menu only a hover opens, beside a link Enter only follows": ([(
        "<nav><a href=\"#home\">Home</a> <a href=\"#docs\">Docs</a></nav>",
        "<style>.more ul { display: none } .more:hover ul { display: block }</style><nav><a href=\"#home\">Home</a> "
        "<a href=\"#docs\">Docs</a> <span class=more><a href=\"#shop\">Shop</a><ul><li><a href=\"#blog\">Blog</a>"
        "</li></ul></span></nav>")], "keyboard"),
    "a link Tab reaches inside aria-hidden": ([("<div class=spin></div>", "<div class=spin></div><div aria-hidden=true>"
                                                "<a href='#ghost'>Ghost link</a></div>")], "keyboard"),
    "a picture link out of the Tab order that goes where no other link does": ([(
        "<div class=spin></div>", "<div class=spin></div><a href='#photo' tabindex=-1><img src='big.png' alt='' "
        "style='width: 100px; height: 50px'></a><a href='#story'>The story</a>")], "keyboard"),
    # aria-hidden on a control in view doesn't excuse it from the keyboard.
    "a close button in view that only a mouse can use": ([(
        "<div class=spin></div>", "<div class=spin></div><p id=note>Cookies help us. <button tabindex=-1 "
        "aria-hidden=true onclick=\"note.hidden = true\">Close</button></p>")], "keyboard"),
    "a div button that ignores Enter": ([("<button>Get started</button>",
                                          "<div role=button tabindex=0 onclick=\"this.textContent = 'Started'\">"
                                          "Get started</div><style>[role=button]:focus-visible { outline: 3px "
                                          "solid #05f }</style>")], "keyboard"),
    "a focus ring its card clips": ([(".card { cursor: pointer; padding: 8px; border: 1px solid #ccc; }",
                                      ".card { cursor: pointer; padding: 8px; border: 1px solid #ccc; overflow: "
                                      "hidden; } .card a { display: block; margin: -8px; padding: 8px; }")], "focus"),
    "a custom checkbox with no focus style": ([("<div class=spin></div>",
                                                "<div class=spin></div><label style='cursor: pointer'><input "
                                                "type=checkbox style='position: absolute; opacity: 0'><span "
                                                "style='display: inline-block; width: 14px; height: 14px; border: "
                                                "2px solid #555'></span> Updates</label>")], "focus"),
    "an SVG that spins by itself": ([("<div class=spin></div>",
                                      "<svg width=20 height=20><rect width=20 height=20 fill='#05f'><animateTransform "
                                      "attributeName=transform type=rotate from='0 10 10' to='360 10 10' dur=2s "
                                      "repeatCount=indefinite /></rect></svg>")], "motion"),
    "slides that change every 3 s": ([("<div class=spin></div>",
                                       "<div class=spin></div><div id=slides>One</div><script>let n = 0; setInterval"
                                       "(() => { slides.className = 'slide-' + (++n % 3); }, 3000)</script>")],
                                     "motion"),
}

PLANTED.update({
    "a button that acts on pointerup": ([("<button>Get started</button>",
                                          "<button onpointerup=\"location.hash = 'go'\">Get started</button>")],
                                        "keyboard"),
    "a background the browser drops": ([("url(big.png) center / cover", "url(big (1).png) center / cover")],
                                       "images"),
    "a marquee": ([("<div class=spin></div>", "<div class=spin></div><marquee>News: the case study is out"
                    "</marquee>")], "motion"),
    "a spinner in a component's shadow root": ([("<div class=spin></div>", "<div class=spin></div><x-spin>"
                                                 "</x-spin><script>customElements.define('x-spin', class extends "
                                                 "HTMLElement { constructor() { super(); this.attachShadow({mode: "
                                                 "'open'}).innerHTML = '<style>i { display: block; width: 20px; "
                                                 "height: 20px; background: #05f; animation: r 1s linear infinite }"
                                                 " @keyframes r { to { transform: rotate(1turn) } }</style><i></i>'"
                                                 " } })</script>")], "motion"),
    "a component taken out of the Tab order": ([("<button>Get started</button>", "<button>Get started</button>"
                                                 + "<x-copy tabindex=-1></x-copy>" + COMPONENT)], "keyboard"),
    "focus guards that keep Tab in a form": ([("<button>Get started</button>",
                                               "<button>Get started</button><form><span id=g1 tabindex=0></span><input "
                                               "id=email aria-label=Email><button id=join type=button>Join</button><span "
                                               "id=g2 tabindex=0></span></form><style>input:focus-visible { outline: 3px "
                                               "solid #05f }</style><script>g1.onfocus = () => join.focus(); "
                                               "g2.onfocus = () => email.focus();</script>")], "keyboard"),
    "a picture in a component that doesn't load": ([('<img src="big.png" alt="">', "<x-shot></x-shot><script>"
                                                     "customElements.define('x-shot', class extends HTMLElement { "
                                                     "connectedCallback() { this.attachShadow({mode: 'open'}).innerHTML "
                                                     "= '<img src=gone.png alt=\"\" style=\"width: 300px; height: 150px; "
                                                     "display: block\">' } })</script>")], "images"),
    "an SVG that holds a small picture": ([('src="big.png"', 'src="small.svg"')], "images"),
    "a canvas not scaled for the screen": ([("<div class=spin></div>", "<div class=spin></div><canvas width=300 "
                                             "height=150 style='width: 300px; height: 150px; max-width: 100%'>"
                                             "</canvas>")], "images"),
    "a button held disabled until a mouse moves": ([("<button>Get started</button>", "<button>Get started</button>"
                                                     "<button id=send disabled>Send</button><script>addEventListener("
                                                     "'mousemove', () => { send.disabled = false }, {once: true})"
                                                     "</script>")], "keyboard"),
    "a field its fieldset holds disabled until a mouse moves": ([(
        "<button>Get started</button>", "<button>Get started</button><fieldset id=fs disabled><input aria-label=Name>"
        "</fieldset><style>input:focus-visible { outline: 3px solid #05f }</style><script>addEventListener('mousemove', "
        "() => { fs.disabled = false }, {once: true})</script>")], "keyboard"),
    # Neither Tab nor Shift+Tab gets out of the frame.
    "a frame Tab can't leave": ([("<div class=spin></div>", "<div class=spin></div><iframe title=Links width=300 "
                                  "height=60 srcdoc=\"<a id=one href='#a'>One</a> <a id=two href='#b'>Two</a><script>"
                                  "two.onkeydown = e => { if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); "
                                  "one.focus() } }; one.onkeydown = e => { if (e.key === 'Tab' && e.shiftKey) { "
                                  "e.preventDefault(); two.focus() } }</script>\"></iframe>")], "keyboard"),
    # Focus comes back a moment after Tab or Shift+Tab takes it away.
    "a button that takes focus back 100 ms after losing it": ([(
        "<button>Get started</button>", "<button>Get started</button><button id=hold onblur=\"setTimeout(() => "
        "this.focus(), 100)\">Hold</button>")], "keyboard"),
    # The page names a key to leave the editor, and it doesn't.
    "an editor whose named key doesn't let go": ([("<div class=spin></div>", "<div class=spin></div><p>Press Ctrl+M "
                                                   "to leave the editor.</p><textarea id=ed aria-label=Code></textarea>"
                                                   "<style>textarea:focus-visible { outline: 3px solid #05f }</style>"
                                                   "<script>ed.onkeydown = e => { if (e.key === 'Tab') "
                                                   "e.preventDefault() }</script>")], "keyboard"),
    # A key that only scrolls the page, and a clock that ticks, aren't a key working.
    "a div button only a click works, on a long page": ([(
        "<div class=spin></div>", "<div class=spin></div>" + DIV_BUTTON.format("") + "<div style='height: 3000px'>"
        "</div>")], "keyboard"),
    "a div button only a click works, beside a clock": ([(
        "<div class=spin></div>", "<div class=spin></div>" + DIV_BUTTON.format("") + CLOCK)], "keyboard"),
    "a handle only a drag moves": ([("<button>Get started</button>", "<button>Get started</button>" + HANDLE)],
                                   "keyboard"),
    "an image-set() whose 2x file is missing": ([("url(big.png) center / cover", "image-set(url(small.png) 1x, "
                                                  "url(gone.png) 2x) center / cover")], "images"),
    "a fixed background the screen stretches": ([("url(big.png) center / cover", "url(big.png) center / cover "
                                                  "fixed")], "images"),
    "an image a fade-in never shows": ([('<img src="big.png" alt="">', '<img src="big.png" alt="" style="opacity: '
                                         '0; transition: opacity .4s">')], "images"),
    "a list only drag and drop reorders": ([("<div class=spin></div>", "<div class=spin></div><ol><li draggable=true>"
                                             "Speed</li><li draggable=true>Cost</li></ol>")], "keyboard"),
    "a read-only date field only a click opens": ([("<button>Get started</button>", "<button>Get started</button>"
                                                    "<input id=day readonly aria-label=Day onclick='cal.hidden = false'>"
                                                    "<p id=cal hidden>November</p><style>input:focus-visible { outline: "
                                                    "3px solid #05f }</style>")], "keyboard"),
    "a dialog no key closes": ([("<button>Get started</button>", "<button onclick=\"box.hidden = false; "
                                 "document.querySelector('main').inert = true\">Get started</button>"),
                                ("</main>\n", "</main>\n<div id=box hidden style='position: fixed; inset: 0; background: "
                                 "#0006' onclick='this.hidden = true'><p style='background: #fff'>Demo <a href='#t'>"
                                 "Transcript</a></p></div>\n")], "keyboard"),
    "a background a later gradient replaces": ([("url(big.png) center / cover\"", "url(big.png) center / cover; "
                                                 "background-image: linear-gradient(#fff, #ccc)\"")], "images"),
    "an SVG that links to its picture": ([('src="big.png"', 'src="linked.svg"')], "images"),
    "suggestions only a mouse can pick": ([("<button>Get started</button>", "<button>Get started</button>" + SUGGEST)],
                                          "keyboard"),
    "a menu that closes before Tab reaches it": ([("<button>Get started</button>", "<button>Get started</button>"
                                                   "<button id=more>More</button>"),
                                                  ("</main>\n", "</main>\n<div id=menu hidden><a href='#guides'>Guides"
                                                   "</a></div><script>more.onclick = () => { menu.hidden = false }; "
                                                   "addEventListener('focusin', e => { if (e.target !== more && "
                                                   "!menu.contains(e.target)) menu.hidden = true })</script>\n")],
                                                 "keyboard"),
    "a link a form's Enter blocker cancels": ([("<button>Get started</button>", "<button>Get started</button><form "
                                                "onkeydown=\"if (event.key === 'Enter') event.preventDefault()\"><a "
                                                "href='#sample'>See a sample</a></form>")], "keyboard"),
    "a box only the mouse wheel scrolls": ([("<div class=spin></div>", "<div class=spin></div>" + WHEEL.format(""))],
                                           "keyboard"),
    "rows only a double-click opens": ([("<button>Get started</button>", "<button>Get started</button><p id=row "
                                         "tabindex=0>report.pdf</p><style>#row:focus-visible { outline: 3px solid "
                                         "#05f }</style><script>row.addEventListener('dblclick', () => { "
                                         "row.textContent = 'Opened' })</script>")], "keyboard"),
    "a div a script makes clickable": ([("<div class=spin></div>", "<div class=spin></div><div id=tile>Pricing</div>"
                                         "<script>tile.addEventListener('click', () => { location.hash = 'pricing' })"
                                         "</script>")], "keyboard"),
    "a picture whose mask doesn't load": ([('<img src="big.png" alt="">', '<img src="big.png" alt="" style='
                                            '"mask-image: url(gone.png); -webkit-mask-image: url(gone.png)">')],
                                          "images"),
    "fields a sticky bar covers when they have focus": ([("<div class=spin></div>", "<div class=spin></div>"
                                                          + STICKY.format(""))], "focus"),
    "a box with no height, since its aspect-ratio isn't valid CSS": ([("width: 300px; height: 150px; max-width: 100%;"
                                                                       " background", "width: 300px; aspect-ratio: "
                                                                       "2:1; max-width: 100%; background")], "images"),
    "a label that opens a file picker on a click only": ([("<button>Get started</button>", "<button>Get started</button>"
                                                           + PICKER.format(""))], "keyboard"),
    "tabs only a click switches": ([("<button>Get started</button>", "<button>Get started</button>"
                                     + TABS.format(""))], "keyboard"),
    "a list box whose options act on a click only": ([("<button>Get started</button>", "<button>Get started</button>"
                                                       + LISTBOX.format("for (const o of industry.options) "
                                                                        "o.addEventListener('click', () => { "
                                                                        "results.textContent = o.text })"))],
                                                     "keyboard"),
    "a logo on a span, laid out inline": ([("<div class=spin></div>", "<div class=spin></div>" + LOGO.format(""))],
                                          "images"),
    "a div button only a click takes off the site": ([("<button>Get started</button>", "<div role=button tabindex=0 "
                                                       "onclick=\"location.href = 'https://elsewhere.test/demo'\">Book a "
                                                       "demo</div><style>[role=button]:focus-visible { outline: 3px "
                                                       "solid #05f }</style>")], "keyboard"),
    "a pale focus ring": ([(RING, "a:focus-visible, button:focus-visible { outline: 2px solid #ccc; outline-offset: "
                                  "2px; }")], "focus"),
    "a card whose focus ring is the colour behind it": ([(CARD, FOCUS_WITHIN.format("#fff"))], "focus"),
})

# A field that takes focus back when it's left empty traps Tab, but it shows focus, so only
# the keyboard gate fails.
PLANTED["a field that takes focus back"] = ([(
    "<button>Get started</button>", "<button>Get started</button><input id=name onblur=\"if (!this.value) "
    "setTimeout(() => this.focus())\"><style>input:focus-visible { outline: 3px solid #05f }</style>")],
    "keyboard")

# Pages that are still good, and must pass every gate. A button that pulses still shows focus,
# and Tab still reaches everything above a field that takes focus as the page loads.
STILL_GOOD = {
    "a button that pulses": [("<div class=spin></div>", "<div class=spin></div><script>document.querySelector"
                              "('button').animate([{transform: 'scale(1)'}, {transform: 'scale(1.05)'}], "
                              "{duration: 900, iterations: Infinity})</script>")],
    "a field with autofocus partway down": [("<img src=", "<input autofocus aria-label=Search><style>"
                                             "input:focus-visible { outline: 3px solid #05f }</style><img src=")],
    "a component with its own button": [("<button>Get started</button>", "<button>Get started</button><x-copy>"
                                         "</x-copy>" + COMPONENT)],
    "a canvas scaled for the screen": [("<div class=spin></div>", "<div class=spin></div><canvas id=chart style='"
                                        "width: 300px; height: 150px; max-width: 100%'></canvas><script>chart.width = "
                                        "300 * devicePixelRatio; chart.height = 150 * devicePixelRatio</script>")],
    "an SVG that holds a big picture": [('src="big.png"', 'src="big.svg"')],
    "a slider the arrow keys move": [("<button>Get started</button>", "<button>Get started</button>" + HANDLE + KEYS)],
    "a carousel that fades between slides": [('<img src="big.png" alt="">', '<div style="position: relative"><img '
                                              'src="big.png" alt=""><img src="big.png" alt="" style="position: absolute;'
                                              ' inset: 0; opacity: 0"></div>')],
    "a picture a hover shows": [('<img src="big.png" alt="">', '<style>.peek img { opacity: 0 } .peek:hover img { '
                                 'opacity: 1 }</style><div class=peek><img src="big.png" alt=""></div>')],
    "an image-set() with both files": [("url(big.png) center / cover", "image-set(url(small.png) 1x, url(big.png) 2x)"
                                        " center / cover")],
    "a radio group": [("<button>Get started</button>", "<button>Get started</button><label><input type=radio "
                       "name=plan checked> Starter</label><label><input type=radio name=plan> Team</label><style>"
                       "input:focus-visible { outline: 3px solid #05f }</style>")],
    "a dialog Escape closes": [("<button>Get started</button>", "<button onclick='talk.showModal()'>Get started"
                                "</button><dialog id=talk><p>Hello</p></dialog>")],
    "a combobox the down arrow opens": [("<button>Get started</button>", "<button>Get started</button><input "
                                         "role=combobox aria-label=City readonly onclick='list.hidden = false' "
                                         "onkeydown=\"if (event.key === 'ArrowDown') list.hidden = false\"><p id=list "
                                         "hidden>Oslo</p><style>input:focus-visible { outline: 3px solid #05f }"
                                         "</style>")],
    "a background with a gradient over its picture": [("url(big.png) center / cover", "linear-gradient(transparent, "
                                                       "#0003), url(big.png) center / cover")],
    "suggestions the down arrow moves through": [("<button>Get started</button>", "<button>Get started</button>"
                                                  + SUGGEST + ARROWS)],
    "a menu Tab reaches": [("<button>Get started</button>", "<button>Get started</button><button "
                            "onclick='list.hidden = false'>More</button><div id=list hidden><a href='#guides'>Guides</a>"
                            "</div>")],
    "a form that blocks Enter only in its field": [("<button>Get started</button>", "<button>Get started</button><form>"
                                                    "<input aria-label=Email onkeydown=\"if (event.key === 'Enter') "
                                                    "event.preventDefault()\"><a href='#sample'>See a sample</a></form>"
                                                    "<style>input:focus-visible { outline: 3px solid #05f }</style>")],
    "a box the wheel scrolls that holds a link": [("<div class=spin></div>", "<div class=spin></div>"
                                                   + WHEEL.format("<a href='#all'>All notes</a>"))],
    "a picture with a mask that loads": [('<img src="big.png" alt="">', '<img src="big.png" alt="" style="mask-image: '
                                          'url(big.png); -webkit-mask-image: url(big.png)">')],
    "a sticky bar that focus scrolls clear of": [("<div class=spin></div>", "<div class=spin></div>"
                                                  + STICKY.format("scroll-padding-bottom: 48px"))],
    "a button disabled until its form is filled": [("<button>Get started</button>", "<button>Get started</button>"
                                                    "<input id=mail aria-label=Email oninput='send.disabled = !this.value'>"
                                                    "<button id=send disabled>Send</button><style>input:focus-visible "
                                                    "{ outline: 3px solid #05f }</style>")],
    "a label Enter opens a file picker from": [("<button>Get started</button>", "<button>Get started</button>"
                                                + PICKER.format("onkeydown=\"if (event.key === 'Enter') brief.click()\""))],
    "tabs the arrow keys switch": [("<button>Get started</button>", "<button>Get started</button>" + TABS.format(
        "tabs.onkeydown = e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { const next = "
        "document.activeElement === t1 ? t2 : t1; next.click(); next.focus() } };"))],
    "a list box that acts on a change": [("<button>Get started</button>", "<button>Get started</button>"
                                          + LISTBOX.format("industry.onchange = () => { results.textContent = "
                                                           "industry.value }"))],
    "a logo on a span, laid out inline-block": [("<div class=spin></div>", "<div class=spin></div>"
                                                 + LOGO.format("display: inline-block;"))],
    # Each probe starts as a first visit, so the banner a probe before accepted is back.
    "a cookie banner that hides once accepted": [("<main>\n", "<main>\n" + CONSENT)],
    # A key that starts a navigation acts, though the page it leaves can't be read after.
    "a button that takes Enter off the site": [("<button>Get started</button>", "<button onclick=\"location.href = "
                                                "'https://elsewhere.test/demo'\">Book a demo</button>")],
    "a link off the site under a key listener": [("<button>Get started</button>", "<button>Get started</button><div "
                                                  "onkeydown=\"if (event.key === 'Escape') this.blur()\"><a href="
                                                  "'https://elsewhere.test/demo'>Book a demo</a></div>")],
    # Focus is pictured with animations held as the screenshot holds them: one that ended, at its end.
    "links in a hero that rose in as the page loaded": [("<nav>", "<style>.hero { animation: rise .4s ease-out both } "
                                                         "@keyframes rise { from { transform: translateY(60px); opacity: 0 "
                                                         "} }</style><nav class=hero>")],
    "a ring that fades in": [(RING, "a:focus-visible, button:focus-visible { outline: none; box-shadow: 0 0 0 3px "
                                    "#05f; } a, button { transition: box-shadow .4s; }")],
    # What is on top of a stop covers it only if it paints there, and a wrapped link is its lines.
    "a see-through layer over the top of the page": [("<main>\n", "<main>\n<div style='position: fixed; inset: 0 0 auto "
                                                      "0; height: 400px; z-index: 5'></div>")],
    "a card whose title link stretches over it": [(CARD, "<div class=story><h3><a class=main href='#story'>The story</a>"
                                                   "</h3><p>By <a href='#author'>the author</a></p></div><style>.story { "
                                                   "position: relative; padding: 16px; border: 1px solid #ccc } .story "
                                                   ".main::after { content: ''; position: absolute; inset: 0 }</style>")],
    "links that wrap in a paragraph": [("<div class=spin></div>", "<div class=spin></div>" + WRAPPING)],
    "a row of cards that scrolls smoothly to the one with focus": [("<div class=spin></div>", "<div class=spin></div>"
                                                                    + ROW)],
    "a skip link that slides in with focus": [("<main>\n", "<a class=skip href='#docs'>Skip to the docs</a><style>.skip "
                                               "{ position: absolute; left: 8px; top: -60px; transition: top .3s } "
                                               ".skip:focus { top: 8px }</style>\n<main>\n")],
    "a skip link hidden in a 1 px box until it has focus": [("<main>\n", "<a class=skip href='#docs'>Skip to the "
                                                             "docs</a><style>.skip:not(:focus) { position: absolute; "
                                                             "width: 1px; height: 1px; overflow: hidden; clip-path: "
                                                             "inset(50%) } .skip:focus { display: block; padding: 8px "
                                                             "16px; outline: none; background: #003a99; color: #fff }"
                                                             "</style>\n<main>\n")],
    "a link off the pixel grid that focus fills pale behind dark text": [("<div class=spin></div>",
                                                                          OFF_GRID.format("#000"))],
    "slides a carousel shows on scrolling": [("<div class=spin></div>", SLIDES.format(""))],
    "a slide a script fades up with focus": [("<div class=spin></div>", SCRIPTED.format(
        "opacity: .4", "<a href='#f'>Fades up</a>", "opacity", ".4 + .6 * t"))],
    # Focus can show on a box around the stop, and as a change of colour that reaches 3:1.
    "a card that shows focus around itself": [(CARD, FOCUS_WITHIN.format("#05f"))],
    "a button that darkens with focus": [("<button>Get started</button>", "<button class=dark>Get started</button>"
                                          "<style>.dark:focus-visible { outline: none; background: #003a99; color: #fff }"
                                          "</style>")],
    # A hover opens the menu, and so does Enter on the button beside its link.
    "a menu a hover opens and its button opens too": [(
        "<nav><a href=\"#home\">Home</a> <a href=\"#docs\">Docs</a></nav>",
        "<style>.menu ul { display: none } .menu:hover ul, .menu.open ul { display: block }</style><nav><a "
        "href=\"#home\">Home</a> <a href=\"#docs\">Docs</a> <span class=menu id=m><a href=\"#shop\">Shop</a><button "
        "aria-expanded=false onclick=\"m.classList.toggle('open'); this.ariaExpanded = m.classList.contains('open')\">"
        "More</button><ul><li><a href=\"#blog\">Blog</a></li></ul></span></nav>")],
    # A link only a mouse reaches that goes where a link Tab reaches goes, and a slide out of view.
    "a card whose picture repeats its title link": [("<div class=spin></div>", "<div class=spin></div><div><a "
                                                     "href='#story' tabindex=-1 aria-hidden=true><img src='big.png' "
                                                     "alt='' style='width: 100px; height: 50px'></a><h3><a "
                                                     "href='#story'>The story</a></h3></div>")],
    "a carousel's slide out of view, out of the Tab order": [(
        "<div class=spin></div>", "<div class=spin></div><div style='width: 150px; overflow: hidden'><div "
        "style='display: flex; width: 300px'><div style='width: 150px; flex: none'><a href='#s1'>Slide one</a></div>"
        "<div style='width: 150px; flex: none' aria-hidden=true><a href='#s2' tabindex=-1>Slide two</a></div></div>"
        "</div>")],
    # What can't take focus: inert, a disabled fieldset, and the page outside a modal dialog.
    "a region under inert": [("<div class=spin></div>", "<div class=spin></div><div inert><a href='#later'>Later</a> "
                              "<button>Later</button></div>")],
    "fields in a disabled fieldset": [("<div class=spin></div>", "<div class=spin></div><fieldset disabled><input "
                                       "aria-label=Name> <button>Send</button></fieldset>")],
    "a dialog open from the start": [("<div class=spin></div>", "<div class=spin></div><dialog id=welcome><p>Welcome"
                                      "</p><button onclick='welcome.close()'>OK</button></dialog><script>"
                                      "welcome.showModal()</script>")],
    # Tab moves on inside a frame, and through a date field's parts, while the page's focus stays put.
    "a frame with two links": [("<div class=spin></div>", "<div class=spin></div><iframe title=Links width=300 "
                                "height=60 srcdoc=\"<a href='#a'>One</a> <a href='#b'>Two</a>\"></iframe>")],
    "a date field": [("<div class=spin></div>", "<div class=spin></div><label>Day <input type=date></label><style>"
                      "input:focus-visible { outline: 3px solid #05f }</style>")],
    # Loops a key gets out of, as ACT's rules on keyboard traps allow: Escape closes a dialog whose
    # guards keep Tab in it, Shift+Tab leaves two buttons Tab goes round, and the key the page names.
    "a dialog Escape closes, with guards that keep Tab in it": [(
        "<div class=spin></div>", "<div class=spin></div><span id=g1 tabindex=0 aria-hidden=true></span><div id=box "
        "role=dialog aria-modal=true aria-label=Welcome><input id=first aria-label=Name> <button id=done>Done"
        "</button></div><span id=g2 tabindex=0 aria-hidden=true></span><style>input:focus-visible { outline: 3px "
        "solid #05f }</style><script>g1.onfocus = () => done.focus(); g2.onfocus = () => first.focus(); "
        "done.onclick = () => box.hidden = true; box.onkeydown = e => { if (e.key === 'Escape') box.hidden = true }"
        "</script>")],
    "two buttons Tab goes round, which Shift+Tab leaves": [(
        "<div class=spin></div>", "<div class=spin></div><p><button id=b1>One</button> <button id=b2>Two</button></p>"
        "<script>b2.onkeydown = e => { if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); b1.focus() } }"
        "</script>")],
    "an editor that keeps Tab until the key its text names": [(
        "<div class=spin></div>", "<div class=spin></div><p>Press Ctrl+M to leave the editor.</p><textarea id=ed "
        "aria-label=Code></textarea><style>textarea:focus-visible { outline: 3px solid #05f }</style><script>"
        "let keep = true; ed.onkeydown = e => { if (e.ctrlKey && e.key === 'm') { keep = false; e.preventDefault() } "
        "else if (e.key === 'Tab' && keep) e.preventDefault() }</script>")],
    "a div button the keys work, beside a clock": [(
        "<div class=spin></div>", "<div class=spin></div>" + DIV_BUTTON.format(
            " onkeydown=\"if (event.key === 'Enter' || event.key === ' ') this.click()\"") + CLOCK)],
}
WIDTH = 390  # a phone, where the wide block runs off


def png(width, height):
    """A grey PNG of that size."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + b"\x88" * (width * 3) for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def site(root, name, changes=()):
    html = GOOD
    for old, new in changes:
        assert html.count(old) == 1, f"the plant has to change the page once: {old!r}"
        html = html.replace(old, new)
    folder = Path(root) / name.replace(" ", "-").replace("'", "")
    folder.mkdir()
    (folder / "index.html").write_text(html, encoding="utf-8")
    (folder / "big.png").write_bytes(png(600, 300))  # sharp at 2x for 300x150
    (folder / "small.png").write_bytes(png(150, 75))
    for name, (width, height) in {"big": (600, 300), "small": (150, 75)}.items():  # an SVG drawn 300x150
        data = base64.b64encode(png(width, height)).decode()
        (folder / f"{name}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 150" width="300" height="150">'
            f'<image href="data:image/png;base64,{data}" width="300" height="150"/></svg>', encoding="utf-8")
    (folder / "linked.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 150" width="300" '
                                       'height="150"><image href="big.png" width="300" height="150"/></svg>',
                                       encoding="utf-8")
    return folder


class GatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        try:
            cls.browser = cls.stack.enter_context(exercise.chromium())
        except exercise.ExerciseError as err:
            raise unittest.SkipTest(str(err)) from None
        cls.root = Path(cls.stack.enter_context(tempfile.TemporaryDirectory()))

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def failing(self, folder, only=gates.GATES):
        results = gates.gates("/", [WIDTH], only=only, browser=self.browser, serve=folder)
        self.assertEqual(sorted(r["gate"] for r in results), sorted(only))
        return {r["gate"]: r for r in results if r["status"] != "pass"}

    def test_the_good_page_passes_every_gate(self):
        self.assertEqual(self.failing(site(self.root, "good")), {})
        for name, changes in STILL_GOOD.items():  # their motion isn't what's tested
            with self.subTest(page=name):
                self.assertEqual(self.failing(site(self.root, name, changes),
                                              tuple(g for g in gates.GATES if g != "motion")), {})

    def test_each_plant_fails_its_own_gate_and_no_other(self):
        # The motion gate watches each page for 11 s, so only the motion plants run it.
        quick = tuple(g for g in gates.GATES if g != "motion")
        for name, (changes, gate) in PLANTED.items():
            with self.subTest(plant=name):
                failed = self.failing(site(self.root, name, changes),
                                      gates.GATES if gate == "motion" else quick)
                self.assertEqual(list(failed), [gate])
                self.assertEqual(failed[gate]["status"], "fail")
                self.assertTrue(failed[gate]["findings"], "a failure names what failed")

    def test_a_finding_names_the_element_and_the_number(self):
        failed = self.failing(site(self.root, "named", PLANTED["a small image drawn large"][0]), ("images",))
        finding = failed["images"]["findings"][0]
        self.assertEqual(finding["path"], "body > main > img")
        self.assertEqual(finding["why"], "drawn 300x150 px, so it needs about 600x300 px at 2x; it has 150x75")
        # Cropped to cover a square, the picture is drawn taller than its box, and its height is short.
        square = [('src="big.png"', 'src="big.png" style="height: 300px; object-fit: cover"')]
        finding = self.failing(site(self.root, "square", square), ("images",))["images"]["findings"][0]
        self.assertEqual(finding["why"], "drawn 300x300 px, cropped to cover it, so it needs about 1200x600 px "
                                         "at 2x; it has 600x300")

    def test_a_trap_names_the_field_that_takes_focus_back(self):
        failed = self.failing(site(self.root, "trap", PLANTED["a field that takes focus back"][0]), ("keyboard",))
        self.assertEqual(failed["keyboard"]["findings"], [{"path": "#name", "why": "Tab can't leave it"}])

    def test_a_slide_that_shows_once_tab_scrolls_to_it_is_judged_by_itself(self):
        failed = self.failing(site(self.root, "slides", PLANTED["slides a carousel shows on scrolling, with no focus "
                                                                 "style"][0]), ("focus",))
        self.assertEqual([f["why"] for f in failed["focus"]["findings"]], ["it looks the same with focus as without"] * 3)

    def test_a_pale_ring_names_its_contrast_and_a_tiny_one_passes_as_weak(self):
        failed = self.failing(site(self.root, "pale", PLANTED["a pale focus ring"][0]), ("focus",))
        self.assertIn({"path": "body > main > button", "why": "its focus change reaches 1.6:1 against the colours "
                       "beside it, and AA asks 3:1"}, failed["focus"]["findings"])
        dot = [("<button>Get started</button>", "<button>Get started</button><a class=dot href='#dot'>Dot only</a><style>"
                ".dot:focus-visible { outline: none } .dot:focus-visible::after { content: ''; display: inline-block; "
                "width: 2px; height: 2px; background: #05f; margin-left: 2px }</style>")]
        results = gates.gates("/", [WIDTH], only=("focus",), browser=self.browser, serve=site(self.root, "dot", dot))
        self.assertEqual(results[0]["status"], "pass")
        self.assertIn("body > main > a", [w["path"] for w in results[0]["weak"]])
        self.assertIn("show it weakly", results[0]["detail"])

    def test_the_focus_figures_of_wcag_1411_and_the_browsers_own_ring(self):
        # Figures 8 to 14 of WCAG 1.4.11's Understanding page, blue buttons on white: 9, a yellow
        # ring outside, 12, a border turned green, and 13, a green ring inside a black border, fail.
        styles = {"f08": "outline: 3px solid #ff0; outline-offset: -8px", "f09": "outline: 3px solid #ff0; outline-offset: 2px",
                  "f11": "outline: 6px solid #ff0; outline-offset: -3px"}
        for px in (1, 2, 3):
            styles.update({f"f10-{px}": f"outline: {px}px solid #008000",
                           f"f12-{px}": "border-color: #4B933A", f"f13-{px}": f"box-shadow: inset 0 0 0 {px}px #008000",
                           f"f14-{px}": f"box-shadow: inset 0 0 0 {px}px #fff"})
        borders = {**{f"f12-{px}": f"border: {px}px solid #4189B9" for px in (1, 2, 3)},
                   **{f"f{n}-{px}": "border: 2px solid #000" for n in (13, 14) for px in (1, 2, 3)}}
        css = "".join(f"#{k} {{ {borders.get(k, 'border: 0')} }} #{k}:focus-visible {{ {v} }}" for k, v in styles.items())
        # The browser's own ring, blue and white, on any background; an author's ring in two colours;
        # and one its box clips to its top side.
        backgrounds = ["#fff", "#000", "#767676", "#4189B9", "#101010", "#005fcc", "#1a73e8"]
        own = "".join(f"<p style='background: {b}; padding: 20px'><a id=own-{n} href='#o{n}' style='color: "
                      f"{'#000' if b == '#fff' else '#fff'}'>Own ring</a></p>" for n, b in enumerate(backgrounds))
        html = ("<!doctype html><style>body { margin: 0; font: 16px sans-serif } button { background: #4189B9; color: #fff;"
                " width: 120px; height: 40px; outline: none; margin: 24px } " + css + " .two:focus-visible { outline: 2px "
                "solid #fff; box-shadow: 0 0 0 4px #000 } .clip { overflow: hidden; padding-top: 4px; display: "
                "inline-block } .clip a { display: block; padding: 6px 10px } .clip a:focus-visible { outline: 2px "
                "solid #05f; outline-offset: 1px }</style><main>" + "".join(f"<button id={k}>{k}</button>" for k in styles)
                + own + "<p style='background: #767676; padding: 20px'><a class=two id=two href='#t' style='color: #fff'>"
                "Two colours</a></p><div class=clip><a id=clipped href='#c'>Clipped</a></div></main>")
        folder = self.root / "figures"
        folder.mkdir()
        (folder / "index.html").write_text(html, encoding="utf-8")
        result = gates.gates("/", [WIDTH], only=("focus",), browser=self.browser, serve=folder)[0]
        self.assertEqual(sorted(f["path"] for f in result["findings"]),
                         ["#f09"] + [f"#f{n}-{px}" for n in (12, 13) for px in (1, 2, 3)])
        weak = {w["path"]: w["why"] for w in result["weak"]}
        self.assertIn("it shows on 1 of 4 sides", weak["#clipped"])

    def test_text_a_script_rewrites_and_a_blinking_caret_arent_motion(self):
        clock = [("<div class=spin></div>", "<div class=spin></div><p id=clock></p><script>setInterval(() => "
                  "{ clock.textContent = new Date().toISOString(); }, 200)</script>")]
        self.assertEqual(self.failing(site(self.root, "clock", clock), ("motion",)), {})
        self.assertEqual(self.failing(site(self.root, "caret", STILL_GOOD["a field with autofocus partway down"]),
                                      ("motion",)), {})

    def test_the_command_exits_1_on_a_failed_gate_and_writes_json(self):
        folder = site(self.root, "command", PLANTED["no focus style"][0])
        out, path = io.StringIO(), self.root / "gates.json"
        browser = mock.patch.object(exercise, "chromium", lambda: nullcontext(self.browser))
        with redirect_stdout(out), redirect_stderr(out), browser:
            code = main(["gates", "/", "--serve", str(folder), "--width", str(WIDTH),
                         "--only", "focus", "--only", "keyboard", "--json", str(path)])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("1 of 2 gates passed", out.getvalue())
        self.assertIn("--- focus at 390 px", out.getvalue())
        saved = json.loads(path.read_text())
        self.assertEqual([r["gate"] for r in saved["results"]], ["keyboard", "focus"])


class StrayNavigationTest(unittest.TestCase):
    """A link a probe followed can land while the next probe loads the page or reads it."""
    STRAY = Exception('Page.goto: Navigation to "http://site.test/" is interrupted by another navigation to '
                      '"http://site.test/next"')

    def test_a_load_a_stray_navigation_interrupts_starts_over_once(self):
        page = mock.MagicMock()
        page.goto.side_effect = [self.STRAY, None]
        gates._fresh(page, "http://site.test/")
        self.assertEqual(page.goto.call_count, 2)
        page.wait_for_load_state.assert_called_once_with("load")

    def test_another_error_or_a_second_stray_navigation_is_raised(self):
        for errors in ([Exception("net::ERR_CONNECTION_REFUSED")], [self.STRAY, self.STRAY]):
            page = mock.MagicMock()
            page.goto.side_effect = errors
            with self.subTest(errors=errors), self.assertRaises(Exception):
                gates._fresh(page, "http://site.test/")

    def test_a_key_after_which_the_page_cant_be_read_is_neither_working_nor_dead(self):
        page = mock.MagicMock()
        page.evaluate.side_effect = [{"before": 1}, Exception("Page.evaluate: Execution context was destroyed")]
        with mock.patch.object(gates, "_fresh"), mock.patch.object(gates, "_locate"):
            self.assertIsNone(gates._acts(page, "http://site.test/", "#logo", "Enter"))


class WidthsTest(unittest.TestCase):
    def test_widths_come_from_the_flag_then_the_baselines_frames_then_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "design"
            self.assertEqual(gates.widths_from(baseline), [1280, 390])
            design.write_json(baseline / "index.json", {"format": 1, "sets": {}, "frames": {
                "1:2": {"name": "web", "width": 1440}, "1:3": {"name": "phone", "width": 375},
                "1:4": {"name": "web again", "width": 1440}}})
            self.assertEqual(gates.widths_from(baseline), [1440, 375])
            self.assertEqual(gates.widths_from(baseline, [768]), [768])

    def test_an_unknown_gate_is_refused(self):
        with self.assertRaises(gates.GateError):
            gates.gates("/", [390], only=["contrast"], browser=object())


# The in-page scripts the page runs, each put together from pieces in gates_js/. HELPERS and _PAIR
# are pieces of the others, so they're parsed inside them.
SCRIPTS = {name: value for name, value in vars(gates).items()
           if name.isupper() and isinstance(value, str) and "=>" in value
           and name not in ("HELPERS", "_PAIR")}


@unittest.skipUnless(shutil.which("node"), "needs node to parse the in-page scripts")
class ScriptsTest(unittest.TestCase):
    def parses(self, script):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.js"
            path.write_text(f"({script});\n", encoding="utf-8")
            done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        return done.returncode == 0, done.stderr

    def test_every_script_parses(self):
        self.assertGreater(len(SCRIPTS), 30)
        for name, script in SCRIPTS.items():
            with self.subTest(script=name):
                ok, error = self.parses(script)
                self.assertTrue(ok, error)

    def test_a_script_that_doesnt_parse_is_caught(self):
        self.assertFalse(self.parses(gates.CLICKABLE[:-1])[0])  # its closing brace cut off
        self.assertTrue(self.parses(gates.CLICKABLE)[0])

    def test_every_piece_is_used_and_every_one_used_exists(self):
        source = Path(gates.__file__).read_text(encoding="utf-8")
        named = set(re.findall(r'_js\("([^"]+)"\)', source))
        on_disk = {path.stem for path in gates.JS.glob("*.js")}
        self.assertEqual(on_disk, named)


def set_twice(source):
    """The names a module sets more than once at its top level, where a later one silently
    replaces an earlier one: a script's name taken again for a number, say."""
    names = [target.id for node in ast.parse(source).body if isinstance(node, (ast.Assign, ast.AnnAssign))
             for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
             if isinstance(target, ast.Name)]
    return sorted({name for name in names if names.count(name) > 1})


class RatioTest(unittest.TestCase):
    def test_a_contrast_just_short_of_aa_never_prints_as_aa(self):
        self.assertEqual([gates._ratio(r) for r in (2.96, 2.999, 3.0, 2.3, 1.606, 21.0)],
                         ["2.9", "2.9", "3.0", "2.3", "1.6", "21.0"])
        self.assertEqual(f"{2.96:.1f}", "3.0")  # what a finding printed before


class NamesTest(unittest.TestCase):
    def test_no_name_is_set_twice_at_the_top_of_gates(self):
        self.assertEqual(set_twice(Path(gates.__file__).read_text(encoding="utf-8")), [])

    def test_a_name_set_twice_is_caught(self):
        self.assertEqual(set_twice('CHANGES = "() => {}"\nOTHER = 1\nCHANGES = 2\n'), ["CHANGES"])


if __name__ == "__main__":
    unittest.main()
