# v1 → v2 Breaking Changes

This document lists breaking changes when upgrading from IPAM v1.x to v2.0.

**Upgrade steps:** pull/deploy the v2 image or code, restart the application. Database migrations run automatically on startup via `init_db()`. No manual SQL is required for standard upgrades.

---

## Removed features

| Feature | v1 | v2 |
|---------|----|----|
| Response caching / rate limiting | Flask-Limiter + in-app cache layer | Removed — direct DB queries |
| In-app update checker | `/check_update` + header toast | Removed — check releases yourself |
| Feature flags | Admin toggles for racks, tags, IP notes, bulk ops | Removed — features always available, gated by permissions only |
| Backup & restore | Admin UI + `/backup/*` routes | Removed — use your own DB backup strategy |
| Help page | `/help` | Removed |
| Interactive API docs | `/api-docs` web page | Removed — see [API.md](API.md) |
| Custom field “searchable” flag | UI checkbox + DB column | Removed — was never wired to search |

### Dependencies removed

- `requests` (update checker)
- `Flask-Limiter` and the custom cache module (already gone in v2 prep)

---

## Removed routes

| Method | v1 path | Notes |
|--------|---------|-------|
| GET | `/check_update` | Update checker |
| GET/POST | `/backup`, `/backup/create`, `/backup/download/<file>`, `/backup/restore`, `/backup/delete/<file>` | Backup UI |
| GET | `/help` | Help page |
| GET | `/api-docs` | Swagger-style docs |
| GET/POST | `/admin/feature_flags` | Feature flag toggles |
| GET | `/custom_fields/<entity_type>` | Duplicate of API; use `/api/v1/custom_fields/{entity_type}` |
| GET | `/api/device/<id>/ip_history` | Moved — see below |
| GET | `/api/ip/<ip>/history` | Moved — see below |

---

## API changes

### Version

`GET /api/v1/info` now reports `"api_version": "2.0"`.

### IP history endpoints

| v1 (removed) | v2 replacement | Auth |
|--------------|----------------|------|
| `GET /api/device/<id>/ip_history` | `GET /api/v1/devices/<id>/ip_history` | API key (`X-API-Key` or `Authorization: Bearer`) |
| `GET /api/ip/<ip>/history` | `GET /api/v1/ips/<ip>/history` | API key |

The **subnet page UI** uses a session-authenticated web route instead of the old unversioned API paths:

- `GET /ip/<ip>/history` — requires login + `view_subnet` permission

Update any scripts that called the old `/api/device/...` or `/api/ip/...` paths to use the v1 API routes above with an API key.

### Audit logging for API calls

v1 logged **every** API request (including GETs) to the audit log as `api_usage`.

v2 logs **mutating** requests only: `POST`, `PUT`, `DELETE`, `PATCH`. GET traffic is no longer audited. If you relied on GET audit entries for compliance, adjust your monitoring.

---

## Database migrations (automatic)

On startup, v2 runs these migrations against existing databases:

1. **Drop `FeatureFlags` table** — feature flags removed
2. **Drop `CustomFieldDefinition.searchable` column** — if present
3. **Remove orphaned permission `view_help`** — help page removed

No data loss for core IPAM entities (subnets, IPs, devices, racks, tags, users, audit log).

---

## Permissions & sessions

- **`view_help`** permission is removed from the database on upgrade.
- Feature-flag toggles no longer hide UI; use **roles and permissions** instead.
- Permissions are **cached in the session at login**. If an admin changes a user's role, that user must **log out and back in** for permission changes to take effect.

---

## Configuration

No new required environment variables. Removed features did not introduce new config keys.

Docker images no longer need a `/backups` volume mount for in-app backup (remove if you added it only for IPAM backup).

---

## Codebase layout (operators / fork maintainers)

| v1 | v2 |
|----|----|
| `app.py` + `routes.py` + `cache.py` + `totp_utils.py` | Single `app.py` + `db.py` |
| `templates/api_docs.html`, `templates/backup.html`, `templates/help.html` | Deleted |

---

## Recommended pre-upgrade checklist

1. **Back up your MariaDB/MySQL database** using your normal tooling (`mysqldump`, volume snapshot, etc.).
2. Note any integrations using removed routes (update checker, backup API, legacy IP history paths).
3. Deploy v2 and restart the container/process once.
4. Verify login, home page, devices, and one API call with your API key.
5. Have affected users re-login if roles were changed recently.

---

## Questions

For API reference after upgrade, see [API.md](API.md).
