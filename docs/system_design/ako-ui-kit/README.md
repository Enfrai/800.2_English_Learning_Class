# Ako UI starter kit

Files
- `css/tokens.css`      colours, type sizes, spacing (from section 5 of the UI document). Change values here only.
- `css/components.css`  buttons, fields, tables, messages, badges (review, present, absent, corrected), chips, cards, summary figure, menu bar, print rules.
- `components.html`     every component with sample markup. Copy from here.
- `layout-phone.html`   one-column 360 px page (public and learner pages).
- `layout-print.html`   A4 print page (attendance list, report, QR page).

Rules
1. Use the classes, not new colours. Never write a hex value in a page.
2. Buttons and fields are at least 44 px tall (`--control-h`). Body text is 18 px.
3. A message goes directly under the field or button it belongs to. Errors use `role="alert"`.
4. Colour is never the only signal: keep the words in badges and messages.
5. Later features use `btn-later` or `card later` (dashed grey) and are not clickable.
6. Menu bar: mark the current page with `aria-current="page"`. Show only items the user's role may use.
7. Message text is fixed in section 7 of the UI document. Copy it exactly so tests match.

Screens for US-015 to US-017 (correct past attendance, learner history, CSV import) use only these components: tables, check boxes, messages, the present/absent/corrected badges and the summary figure. A file picker is a normal secondary button.

Updated 19 October 2026 for the 17 user stories. Ask the team before adding a new component.
