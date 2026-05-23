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
| Device types | Device type CRUD, `device_type_id` on devices, rack placement filters | Removed — devices are untyped; use tags or custom fields instead |

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
| GET/POST/PUT/DELETE | `/api/v1/device-types`, `/api/v2/device-types` | Device types removed |

---

## API changes

### v2 is API-only + Vue SPA

v2 removes **all Jinja/HTML routes**. The UI is a Vue 3 SPA served from `static/dist/`. All functionality goes through `/api/v2/*`.

| v1 | v2 |
|----|-----|
| `/api/v1/*` | **`/api/v2/*`** (v1 removed) |
| Session via HTML login forms | `POST /api/v2/auth/login` + session cookie |
| API key only on API routes | **Same routes** accept session cookie **or** API key |
| `{ "devices": [...] }` list responses | **`{ "items": [...] }`** for all list endpoints |
| `{ "tags" }`, `{ "users" }`, `{ "roles" }`, `{ "racks" }`, `{ "logs" }`, `{ "fields" }` wrappers | **`{ "items" }`** (audit also includes `total`; devices-by-tag includes `meta`) |

### Version

`GET /api/v2/info` reports `"api_version": "2.0"`.

### IP history endpoints

| v1 (removed) | v2 replacement | Auth |
|--------------|----------------|------|
| `GET /api/device/<id>/ip_history` | `GET /api/v2/devices/<id>/ip-history` | Session or API key |
| `GET /api/ip/<ip>/history` | `GET /api/v2/ips/<ip>/history` | Session or API key |

### Audit logging for API calls

v1 logged **every** API request (including GETs) to the audit log as `api_usage`.

v2 logs **mutating** requests only: `POST`, `PUT`, `DELETE`, `PATCH`. GET traffic is no longer audited. If you relied on GET audit entries for compliance, adjust your monitoring.

---

## Database migrations (automatic)

On startup, v2 runs these migrations against existing databases:

1. **Drop `FeatureFlags` table** — feature flags removed
2. **Drop `CustomFieldDefinition.searchable` column** — if present
3. **Remove orphaned permission `view_help`** — help page removed
4. **Drop `Device.device_type_id` column and `DeviceType` table** — device types removed
5. **Remove device-type permissions** — `view_device_types`, `add_device_type`, etc.

No data loss for core IPAM entities (subnets, IPs, devices, racks, tags, users, audit log). Device type labels are not migrated; use tags or custom fields if you need classification.

---

## Permissions & sessions

- **`view_help`** permission is removed from the database on upgrade.
- **Device-type permissions** (`view_device_types`, `add_device_type`, etc.) are removed on upgrade.
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
| `templates/`, legacy `static/js` | **Deleted** — replaced by `frontend/` → `static/dist/` |
| Server-rendered Tailwind | Vue 3 + Vite + Tailwind (auto light/dark, cyan accents) |

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
