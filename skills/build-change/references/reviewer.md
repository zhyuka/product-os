# Handing a section to section-reviewer

Start one `section-reviewer` per section and width. It has only the Read tool, so it judges the
pictures and numbers, not your account of the build. Give it, as full paths:

- the design picture: `.look/<route>-<width>/design.png`, from the frame's `get_screenshot` or the
  person's picture. Say when it is the frame's own render, so a missing page background is on
  purpose. For a part the design animates, add each step's picture too.
- the build picture from the served build at the same width, uncropped. A tall section can go in
  numbered parts; one image pixel is one CSS pixel.
- the numbers, when the design check ran: save its printed output for that frame to
  `.look/<route>-<width>/numbers.txt`, with this line at the top: "Rows are the design check's MISS
  lines: each names the text, the measure, the design's value and the build's. A row not listed met
  its check." Without the check there are no numbers; say so, and every size is by eye.
- the decisions file from `app.decisions`, when there is one.
- the route, the width, and the frame's node id or the picture's name.

Leave out what you changed, what you expect and any earlier verdict.

Read its answer by its last line:

- `VERDICT: MATCHES`: nothing to send back at this width. It is not the owner's sign-off.
- `VERDICT: SEND BACK`: fix each item the pictures and numbers bear out, then rebuild and re-check;
  that is the next round.
- `VERDICT: ASK DESIGN`: draft the questions for the person. The section isn't done while one is
  open.
- `VERIFICATION NOT RUN: <reason>`: a picture was missing, blank or of the wrong region. Retake
  it and review again; a capture fault is not a build miss, and the review did not run.
