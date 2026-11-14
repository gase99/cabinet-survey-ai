# Release acceptance — NOT READY / DO NOT MERGE PR #1

Statuses: **PASS** = scoped evidence exists; **FAIL** = requirement demonstrably not
satisfied; **BLOCKED** = needs a named external dependency; **NOT TESTED** = no result.
A passing build is not device acceptance. Mocks are never live integration evidence.

## Exact source policy
Initial PR head: `ca5bc6aedb652b268a03dd34438fe995f22b6d13`.
Every initial backend, migration, worker and Flutter check passed at exactly that SHA
(see `evidence/initial-head-checks.json`). Subsequent fixes invalidate that CI proof
for the new head. All workflows now execute on every PR/push and explicitly check
out `${{ github.event.pull_request.head.sha || github.sha }}` rather than a merge ref.
Run `python scripts/check-head-ci.py /tmp/head-ci.json` to fail closed unless every
required workflow/job is complete and successful for the **current** PR head.
The generated report includes exact SHAs and run links; do not reuse an older report.

## Acceptance matrix (pending final remote rerun)

| Item | Status | Evidence / blocker |
| --- | --- | --- |
| Initial head CI | PASS | exact SHA above; initial-head-checks.json |
| New-head complete CI | NOT TESTED | workflow rerun required after all acceptance fixes |
| Auth revocation, refresh replay, password reset sessions | PASS | local regression tests; session migration added |
| Nested ownership / uploads / SVG escaping / credential encryption | PASS | scoped automated regressions, not a complete penetration test |
| Shared auth quota | PASS | local atomic database quota regression; load test NOT TESTED |
| Geometry rectangle/L/U/irregular fixtures | PASS | existing canonical hashes and strengthened geometry regressions |
| Plan/elevation reference consistency | PASS | vertical-wall offset projection assertions |
| Invalid topology, noninteger data, vertical bounds | PASS | test_geometry_acceptance and measurement_integrity |
| Local restart + real API sync/conflict/exports | NOT TESTED | new controller/physical SQLite/real HTTP test must pass remotely |
| Production Web in real Chrome, fa/en capture/reopen | NOT TESTED | browser automation added; waiting remote execution |
| Full disconnected Web shell restart | NOT TESTED | smoke reload currently uses network; no PWA claim |
| APK/AAB build at current head | NOT TESTED | older artifact not valid proof for session/projection changes |
| Physical Android installation/runtime/camera | BLOCKED | no adb, Android SDK or attached physical device available |
| Live AI | BLOCKED | authorized AI_API_KEY/provider endpoint/model absent |
| Live Telegram delivery | BLOCKED | authorized bot token, deployed worker and HTTPS webhook absent |
| Database migration upgrade/check/downgrade | NOT TESTED | new auth migrations require exact-head PostgreSQL rerun |
| Disposable PostgreSQL+asset recovery drill | NOT TESTED | new guarded CI drill; production recovery remains BLOCKED |
| Owner production backup restore | BLOCKED | owner-managed backup, key material and isolated recovery environment absent |
| Print scale / Persian PDF typography | NOT TESTED | physical print calibration absent; font shaping known incomplete |
| Complete scanner, editor, deletion/photo/background sync | FAIL | previously documented missing functionality remains |
| Local cache encryption / shared-device privacy | FAIL | not implemented; cannot be waived by successful builds |
| Production signing, API host, store/deployment | BLOCKED | owner keystore/authorized host/production authorization absent |

## Reproduce live tests only with explicit authorization
1. Use synthetic customer fixtures in an isolated deployment; never production data.
2. Configure AI_PROVIDER=openai_compatible, authorized HTTPS AI_BASE_URL, AI_MODEL and
   server-side AI_API_KEY. Upload a known annotated sketch and verify observed text,
   source regions and unknowns; confirm exports reject unapproved measurements. Record
   model/version, date, request outcome and redacted evidence, never credentials.
3. Deploy the independent worker behind HTTPS on owner-controlled compute, mount
   exports read-only and configure independent ingress/backend secrets. Register the
   webhook using official Bot API on a secure operator machine. Pair a private test
   chat, generate approved PDF/PNG, send and verify actual bytes received. Exercise
   failed delivery, restart, duplicate update and unlink/cancel. Record redacted
   message IDs/statuses; do not include bot-token URLs in logs or reports.
4. Install the development APK on an owner test device, record model/Android version,
   app SHA and camera permission grant/denial, photo capture, process termination,
   offline capture/reopen, reconnection and conflict outcomes in both locales.
5. Production signing, store publication and production deployment are not authorized
   by this acceptance test task and have not been performed.
