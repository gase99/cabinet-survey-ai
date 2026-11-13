# Development candidate notes — 0.1.0 (not release accepted)

## Implemented and verified independently
- Clean-venv backend suite: 82 passing tests.
- Independent worker suite: 4 passing isolated tests; GitHub worker CI passed.
- Initial migration tested locally on SQLite and in CI on PostgreSQL, including
  metadata comparison and downgrade/re-upgrade. Existing create_all databases must
  not be stamped blindly: back up, inspect and migrate their actual schema first.
- Engine SVG goldens cover rectangle, L, U and irregular rooms with opening/utility
  elements. Missing endpoints produce validation errors rather than guessed topology.
- Exports render engine SVG, with tested PDF A3/A4 media boxes and 300-DPI PNG sizes.

## Client verification
Remote Flutter analysis, **12 Flutter tests**, **8 Chrome-platform tests**, production
Web compilation, Android debug APK and release-mode AAB all passed in run
[43436483276](https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276).
[Download build artifacts](https://github.com/gase99/cabinet-survey-ai/actions/runs/43436483276/artifacts/14044115931)
before 2027-02-11. These mobile binaries use development signing and an intentionally
invalid API host, not owner production credentials. Rebuild with the authorized
HTTPS host for connected testing. Device acceptance and live integrations remain
open; successful builds alone do not establish release readiness.

## Required before release acceptance
Independent device/browser acceptance; complete localization; sketch preprocessing;
voice; full geometry editor; synchronization deletion/photo/merge behavior; security
review and rate limits; session revocation and recovery email; local encryption;
provider token accounting/load verification; multi-room export and Persian font shaping;
physical print calibration; backup restore drill; live vision and Telegram tests;
owner signing configuration and authorized production HTTPS deployment.

No production deployment, app-store publication or live external API test is claimed.
