# Development candidate notes — 0.1.0 (not release accepted)

## Implemented and verified independently
- Local backend suite: 71 passing tests.
- Independent worker suite: 4 passing isolated tests; GitHub worker CI passed.
- Initial migration tested locally on SQLite and in CI on PostgreSQL, including
  metadata comparison and downgrade/re-upgrade. Existing create_all databases must
  not be stamped blindly: back up, inspect and migrate their actual schema first.
- Engine SVG goldens cover rectangle, L, U and irregular rooms with opening/utility
  elements. Missing endpoints produce validation errors rather than guessed topology.
- Exports render engine SVG, with tested PDF A3/A4 media boxes and 300-DPI PNG sizes.

## Client verification
Remote Flutter analysis has passed on an earlier commit. Widget-test failures are
under repair; final source revision tests and Web/Android builds must still pass.
Do not interpret CI configuration or authored source as build evidence.

## Required before release acceptance
Independent device/browser acceptance; complete localization; sketch preprocessing;
voice; full geometry editor; synchronization deletion/photo/merge behavior; security
review and rate limits; session revocation and recovery email; local encryption;
provider admin secret storage; multi-room export and Persian font shaping;
physical print calibration; backup restore drill; live vision and Telegram tests;
owner signing configuration and authorized production HTTPS deployment.

No production deployment, app-store publication or live external API test is claimed.
