# Bundled export font

`Vazirmatn-Regular.ttf` and `Vazirmatn-Bold.ttf` are the only fonts used in PDF/PNG exports.
They are embedded (subset) in every PDF. The export code never uses system fonts.

- Source: https://github.com/rastikerdar/vazirmatn, file `fonts/ttf/` at commit
  `6e553e33489a8f9dfaccc76860a2e3f3c1e66de7` (release v33.003).
- License: SIL Open Font License 1.1, see `OFL.txt`. Redistribution with software is allowed.
  Keep the license file next to the fonts.
- Pinned SHA-256 (checked by `app/services/pdf_text.py`; a mismatch or a missing file stops the API at
  startup and fails exports):
  - Regular `b69fd4c680b8f3f225feabcc655a2c585d97627b8f5f5c0f9985e894069f3a56`
  - Bold `f635fdbea28f265de395ba83b4b1570dcf2f58d13c65469e61903b1c2d2ae723`

To update: replace both files from an upstream release, update the digests in
`pdf_text.py` and here, then run `pytest tests/test_export_text_scale.py` and check a
rendered PDF by eye (see `docs/export-output.md`).
