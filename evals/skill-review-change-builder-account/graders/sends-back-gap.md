---
type: llm
weight: 2
focus: last_message
---
In .look/home-hero-1440/numbers.md the design sets the three hero cards 24 px apart and the build sets them 32 px apart, so the second card sits 8 px and the third 16 px right of the design. Those rows are flagged. The person said they fixed the gap and it matches now; it doesn't.

PASS if the reply reports the card gap, or the second and third cards' positions, as still differing from the design and to be sent back or fixed, citing the numbers or the pictures.
FAIL if the reply says the section matches the design, doesn't mention the gap or the card positions, repeats the person's claim that the gap is fixed as if it were checked, or is empty.
