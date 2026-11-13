# Offline storage and synchronization

## Local-first behavior
SQLite is the local source for active field work. Users can create projects, enter measurements, attach photos and generate geometry previews without network access.

## Outbox
Each local mutation creates a durable operation with operation ID, entity ID, base version, payload, timestamp and retry state. Uploads are idempotent.

## Conflict handling
Compare local and server versions. Never silently overwrite measurements or approvals. Conflicts are visible and require a resolution decision. Preserve both revisions and audit the resolver. Support resumable binary uploads where practical.

## Security
Encrypt sensitive local data where platform support permits; use OS secure storage for refresh tokens. Provide logout/device revocation and local cache clearing.
