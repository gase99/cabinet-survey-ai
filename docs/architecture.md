# System architecture — Android only

## Current baseline
Flutter/Dart Android client, Material 3 and Riverpod; FastAPI backend; PostgreSQL server
storage and native SQLite local storage. Web is cancelled (ADR-006). Persian RTL/English.
Online AI remains a server-side provider adapter; deterministic geometry owns coordinates.
PDF/PNG exports are generated server-side. Telegram runs as an independent worker using
Bot API webhooks on owner-controlled compute, not Telegram-hosted application code.

## Logical flow
Android → HTTPS FastAPI → ownership/auth, survey records, sync, AI orchestration,
geometry and exports. PostgreSQL holds synced records; Android SQLite holds local
projects and a transactional outbox. Sync uses versions and explicit conflict states.
Currently sync is manual; photos, deletions and background reconnect are incomplete.

## Trust boundaries
Android input and uploaded media are untrusted; authorization/validation are server-side.
AI output is untrusted proposal data, never approval. Telegram updates are untrusted.
Bot/provider/session signing secrets remain server-side. Android refresh credentials
use platform secure storage; survey SQLite/photos are not encrypted. Customer data
requires access control, retention, backup and transport encryption.

## Canonical model
Project → rooms → connected walls → openings/obstacles, observations, approvals,
drawing versions, assets and history. Plan and elevations are projections of the same
geometry. Some planned entities/workflows remain incomplete; see the delivery report.

## Deployment
PostgreSQL, API, Telegram worker and API/webhook gateway are separate containers in
`deploy/compose.yml`. AI/export currently execute synchronously inside API, not as
separate background services. HTTPS reverse proxy and secrets are owner-managed.
There is no static web bundle, browser database runtime or web deployment service.
