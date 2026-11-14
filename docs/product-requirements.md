# Product requirements

## Goal
Capture accurate customer-site measurements and produce editable, dimensioned 2D cabinet-survey drawings.

## Approved decisions
- Platforms: Android only. Web cancelled by owner on 2026-11-14 (ADR-006).
- AI: online multimodal API behind a provider-neutral backend adapter.
- Outputs: in-app access/download and Telegram delivery.
- Views: top-down overall plan and individual wall elevations.
- Localization: Persian RTL and English.
- Offline: project capture, manual entry, local persistence and deterministic drawing must work offline.

## Workflow
1. Create customer/project and site metadata.
2. Add room outline, connected walls, heights and reference corners.
3. Add doors, windows, columns, beams, gas/water/drain/electrical points, switches, sockets, ventilation, recesses and custom obstacles.
4. Enter observations manually, from voice transcription or annotated sketch images.
5. Review AI proposals against source image/transcript; correct ambiguities.
6. Explicitly approve measurements.
7. Generate plan and elevations from canonical geometry.
8. Edit, version, export PDF/PNG and optionally deliver via Telegram.

## Correctness
- Sketch pixel proportions are not a real-world scale.
- Missing values remain missing and trigger clarification.
- Confidence is advisory; user approval is mandatory.
- Every extracted value stores provenance and source region.
- Invalid topology, overlaps, out-of-wall elements and inconsistent dimensions are surfaced.
- No silent destructive conflict resolution during sync.
