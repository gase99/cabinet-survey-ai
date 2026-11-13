# Development roadmap (phase-gated)

A phase is complete only after implementation, automated tests, manual acceptance evidence and documentation review. Continue autonomously between phases; request input only for genuine blockers or required authorization.

1. Foundation: repository conventions, architecture, CI, environment and contracts.
2. Flutter shell: Android/Web bootstrap, navigation, themes, Persian RTL and English.
3. Projects: customer/project CRUD, local SQLite, server persistence and migrations.
4. Manual survey: rooms, walls, units, openings, obstacles and validation.
5. Text/voice AI: provider abstraction, structured extraction, review and approval.
6. Sketch scanner: camera/gallery, crop/rotate/perspective correction, OCR/Vision and source overlays.
7. Geometry core: topology, coordinates, validation and golden tests.
8. Drawings: top-down plan and individual wall elevations from shared geometry.
9. Editor: select/move/resize, dimensions, undo/redo and drawing versions.
10. Export: print-ready PDF/PNG, A4/A3 and measurement report.
11. Offline sync and security: auth, roles, outbox, conflict resolution and audit.
12. Telegram integration and release: account linking, delivery worker, Docker/VPS deployment, monitoring, backups and Android/Web release.

## Definition of done
No fabricated measurements; approval enforced; geometry golden tests pass; Android and Web tested independently; offline workflows tested disconnected; PDF scale verified; Telegram delivery tested end-to-end on externally hosted worker; security and backups reviewed.

## Verified implementation status
See [project-status.md](project-status.md) for executed tests, remaining gates and known limitations. A passing backend suite does not mark a product phase complete.
