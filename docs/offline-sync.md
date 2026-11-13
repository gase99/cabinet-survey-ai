# Offline storage and synchronization

## Local-first behavior
SQLite is the local source for active field work. Users can create projects, enter measurements, attach photos and generate geometry previews without network access.

## Outbox
Each local mutation creates a durable operation with operation ID, entity ID, base version, payload, timestamp and retry state. Uploads are idempotent.

## Conflict handling
Compare local and server versions. Never silently overwrite measurements or approvals. Conflicts are visible and require a resolution decision. Preserve both revisions and audit the resolver. Support resumable binary uploads where practical.

## Security
Encrypt sensitive local data where platform support permits; use OS secure storage for refresh tokens. Provide logout/device revocation and local cache clearing.

## Current implementation limits and contract
SQLite commits each record, immutable local revision and outbox operation atomically.
Namespaces are per authenticated owner or the separate device-local workspace.
Outbox IDs are stable across retries. Server receipts validate operation identity,
parent ownership and field allowlists; update base versions are mandatory. Parent
IDs and ownership cannot be changed via sync updates. Approval must be a separate
operation containing only `review_status: approved`; dimensional edits reset review.

Client pushes sequentially and blocks dependent entity operations after conflicts.
Explicit keep-server preserves the local record in revision history; explicit
keep-local preserves both snapshots and creates a new operation against the observed
server version, resetting measurement approval. Another intervening write causes a
new conflict, not a blind overwrite.

The `/sync/pull` endpoint is a receipt feed only, limited to 100 entries; it is not
an exhaustive change stream for normal REST mutations. Client currently imports
paginated REST snapshots after push while protecting dirty local entities. Tombstones,
remote deletions, full incremental cursors, image uploads and background reconnect
scheduling remain incomplete. Do not claim full cross-device synchronization yet.
