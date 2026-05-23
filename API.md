# IPAM API v2

All endpoints are JSON under `/api/v2`. The Vue SPA uses **session cookies** (`credentials: include`); automation uses **API keys** (`X-API-Key`, `Authorization: Bearer`, or `?api_key=`).

## Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v2/auth/login` | `{ email, password }` → `{ ok }` or `{ requires_2fa }` / `{ requires_setup }` |
| POST | `/api/v2/auth/verify-2fa` | `{ code, use_backup? }` |
| POST | `/api/v2/auth/setup-2fa` | `{ action: "generate" \| "verify", code? }` |
| POST | `/api/v2/auth/logout` | Clear session |
| GET | `/api/v2/auth/me` | User, permissions, org branding |

## Account

| Method | Endpoint |
|--------|----------|
| GET | `/api/v2/account` |
| POST | `/api/v2/account/change-password` |
| POST | `/api/v2/account/disable-2fa` |
| POST | `/api/v2/account/regenerate-backup-codes` |

## Core resources

List endpoints return `{ "items": [...] }` unless noted.

| Resource | Endpoints |
|----------|-----------|
| Dashboard | `GET /api/v2/dashboard` |
| Search | `GET /api/v2/search?q=` |
| Devices | CRUD + `/ips`, `/tags`, `/ip-history`, `/custom-fields` |
| Subnets | CRUD + `/available-ips`, `/export`, `/dhcp`, `/custom-fields` |
| IP addresses | `PATCH /api/v2/ip-addresses/{id}` (notes) |
| IP history | `GET /api/v2/ips/{ip}/history` |
| Tags | CRUD + device tag assign/remove |
| Racks | CRUD + `/devices`, `/export` |
| Custom fields | CRUD + `POST /custom-fields/reorder` |
| Audit | `GET /audit`, `GET /audit/export` |
| Users & roles | CRUD + `POST /users/{id}/regenerate-api-key` |
| Permissions | `GET /permissions` |
| Bulk | `POST /bulk/assign-ips`, `/create-devices`, `/assign-tags`, `/export-subnets` |

See route handlers in `app.py` for required permissions and request bodies.

## Example

```bash
curl -H "X-API-Key: YOUR_KEY" https://host/api/v2/devices
curl -c cookies.txt -X POST -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}' \
  https://host/api/v2/auth/login
```
