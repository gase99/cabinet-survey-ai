# Export output: font, Persian shaping and print scale

Applies to server exports (`POST /api/v1/exports/{project_id}`), rendered by
`backend/app/services/export_service.py` and `backend/app/services/pdf_text.py`.
The geometry engine (`backend/app/geometry`) and its SVG output are unchanged. This
layer only places that SVG on the page.

## Font

- Only the bundled **Vazirmatn** Regular and Bold fonts are used
  (`backend/app/assets/fonts`, SIL OFL 1.1, pinned SHA-256; source and update steps are in
  that folder's README).
- The PDF embeds subsets of them. Body text, headers and every SVG label switch to Vazirmatn.
- ReportLab's default Helvetica and Times-Roman states are also replaced, so a PDF lists
  only `Vazirmatn-Regular` and `Vazirmatn-Bold`.
- There is no system-font lookup and no fallback. Pillow loads the PNG header font from the
  same file.
- If a font file is missing or does not match its pinned digest:
  - the API refuses to start;
  - any export already queued fails with the generic `Drawing rendering failed` (no file
    paths leak).

## Persian/Arabic shaping and RTL order

- ReportLab and Pillow's basic layout do not shape complex scripts, so text is prepared
  before drawing:
  1. `arabic-reshaper` (3.1.0) picks contextual presentation forms (initial, medial, final,
     isolated) and the lam-alef ligature. ZWNJ (نیم‌فاصله) correctly stops joining.
  2. `python-bidi` (0.6.12, its pure-Python UBA implementation) reorders text into visual
     order and mirrors brackets.
- Number+unit groups ("3000 mm", "900×1200", "3000 mm × 2700 mm") are wrapped in a
  left-to-right embedding first. This keeps each group readable as one unit.
  - Plain UBA would render `دیوار شمالی — 3000 mm × 2700 mm` as
    `mm × 2700 mm 3000 — …`.
  - It would also turn `900×1200` into `1200×900`.
- Header lines whose first strong character is RTL are right-aligned. Text that does not
  contain Persian or Arabic characters is left exactly as it was.
- Persian digits (۰–۹) and Latin digits both render; the bundled font covers all Persian
  letters. Units are always written as `mm` (integer millimetres from the engine).

## Print scale

- Each PDF page draws one view (plan or wall elevation) at a **standard scale**: 1:1, 1:2,
  1:5, 1:10, 1:20, 1:25, 1:50, 1:100, 1:200, 1:250 or 1:500.
  - The renderer picks the largest drawing that fits the free area of the chosen A4/A3
    page.
  - The header says e.g. `Scale 1:20 on A4 — print at 100% / actual size. Dimensions in
    mm.` and the footer repeats the scale.
  - A scale bar gives a round length and its paper length, e.g. `1000 mm (1:20, 50 mm on
    paper)`.
- Engine SVGs give their viewBox in model millimetres, plus a nominal pixel width and height
  whose aspect ratio can differ from the viewBox. svglib ignores `preserveAspectRatio`, so
  earlier exports stretched elevations unevenly.
  - The renderer now sets width and height to the viewBox size, so 1 SVG unit = 1 mm.
  - It then applies one uniform factor of `72 / 25.4 / N` points per mm.
- An SVG without a viewBox has unknown units. It is fitted to the page and labelled
  `NOT TO SCALE — do not measure from this page`.
- If a drawing would not fit even at 1:500, it is also fitted and labelled NOT TO SCALE.
- **PNG** exports are a single overview sheet. Their header says `fitted overview sheet, NOT
  TO SCALE (use the PDF for scaled prints)`.

## How this is verified (automated)

All checks are in `backend/tests/test_export_text_scale.py`. Fixture cases are in
`backend/tests/fixtures/print_scale.json`.

- **Print-scale fixtures:**
  - Real engine SVG is rendered to PDF.
  - The test reads the content stream, tracks the transformation matrix (`q`/`Q`/`cm`), and
    measures the wall rectangle or room outline in PDF points (tolerance 0.01 pt ≈ 0.004 mm).
  - Examples: a 3000 mm wall on A4 at 1:20 is 150.00 mm wide (425.20 pt). A 12000 mm wall
    is at 1:100, 120 mm. A 6000 × 4000 mm plan is at 1:50, 120 × 80 mm. At 1:50, 3000 mm is
    60 mm (170.08 pt).
  - The tests also check the undistorted aspect ratio, the 50 mm scale-bar line, and the
    NOT TO SCALE label for SVGs without units.
- **Shaping:**
  - Exact code-point sequences, e.g. `سلام` → `U+FEE1 U+FEFC U+FEB3`, and ZWNJ handling.
  - Number/unit order inside RTL text.
  - Every shaped code point exists in the bundled font's cmap.
  - The extracted PDF text contains presentation forms and no isolated base Arabic letters.
- **Fonts:**
  - The PDF font list contains only `Vazirmatn(-Bold)` subsets with an embedded
    `/FontFile2`.
  - A missing font fails PDF and PNG export, the API job (generic error) and API startup.
  - A swapped font file fails the digest check.
- **Determinism:**
  - The same input gives byte-identical PDFs.
  - The PNG header is pixel-identical.
  - PNG drawing tiles come from ReportLab's `rl_renderPM` rasteriser. Its glyph
    anti-aliasing varies by up to about 3/255 grey levels between runs, also with
    Helvetica (upstream behaviour). The geometry is identical.
- **Mutation checks during development:**
  - With shaping disabled, 6 tests fail.
  - With the old width/height scaling restored, 6 tests fail (all scale fixtures plus the
    aspect test).

## Verified only visually (not by automated tests)

- **Rendered glyph shapes.** Code points and the embedded font are tested. Whether the
  letters *look* correctly joined was checked by eye once, on a PDF rasterised with
  pdfium (`pypdfium2`, used only during development, not a dependency).
  - That PDF contained `آشپزخانه خانم احمدی`, `دیوار شمالی — 3000 mm × 2700 mm` and
    `پنجره 900×1200` on A4.
  - Letters were joined, words read right-to-left, numbers read left-to-right, and brackets
    were mirrored.
  - Other PDF viewers were not checked.
- **Physical print scale.** Page geometry is exact in the PDF. Whether a printed sheet
  measures 150 mm depends on the printer and on the viewer's "actual size / 100%"
  setting (fit-to-page shrinks it). No paper print was measured. Always check against the
  scale bar.
- **Label placement.** Plan labels sit on wall midpoints and can overlap walls or each other
  (e.g. a window label near a wall label). Positions come from `backend/app/geometry`,
  which Phase 5 must not change, so this is unchanged and was only reviewed visually.
- **Text extraction / copy-paste.** Text copied from a PDF yields presentation forms in
  visual order. That is expected for shaped text and is not a goal; it can look reversed in
  some viewers' search or copy.
- **Android device.** Exports were not opened on a physical device.
