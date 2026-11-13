# Flutter client scaffold

Android + Web Flutter application. This directory is a foundation scaffold; project capture, drawing editor, camera pipeline, offline sync and AI review are not implemented yet.

Planned modules:
- `lib/app`: bootstrap, theme, localization and routing.
- `lib/features/projects`: customer and project management.
- `lib/features/survey`: room, wall, measurement and obstacle capture.
- `lib/features/sketch_scan`: camera/gallery, image correction and AI review.
- `lib/features/drawing`: shared plan/elevation viewer and editor.
- `lib/features/sync`: offline queue and conflict handling.
- `lib/features/export`: PDF/PNG generation and sharing.
- `lib/core`: database, networking, permissions and common UI.

Run `flutter create . --platforms=android,web` here when Flutter SDK is available, then add dependencies in reviewed commits.
