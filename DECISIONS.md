## Decision Log

### Slack SDK over Webhooks
Reason: Need thread_ts, richer API (files, threads), better errors. Webhooks lack thread control.

### Channel IDs over Names
Reason: Many APIs require IDs (uploads, history). Avoid `channel_not_found`.

### files_upload_v2 (external upload flow)
Reason: `files.upload` deprecated. v2 supports modern upload pipeline and larger files.

### Private uploads (no public URLs)
Reason: Security; avoid `files_sharedPublicURL`. Keep files scoped to workspace.

### Socket Mode preferred
Reason: Real-time events, no polling scopes, simpler logic. Polling only as fallback.

### Config via YAML + env expansion
Reason: Portability; avoid hardcoding secrets/paths. Supports `~` and `${VARS}`.


