# IPAM API Documentation

REST API for programmatic access to IPAM. All endpoints live under `/api/v1`.

## Authentication

Every request requires an API key. Generate or regenerate keys from **Admin → Users** in the web UI.

Provide the key in one of three ways:

| Method | Example |
|--------|---------|
| Header | `X-API-Key: your_api_key` |
| Authorization header | `Authorization: Bearer your_api_key` |
| Query parameter | `?api_key=your_api_key` |

Verify credentials with:

```http
GET /api/v1/info
X-API-Key: your_api_key
```

## Permissions

Endpoints use the same role-based permissions as the web UI. If a user lacks the required permission, the API returns `403 Forbidden` with details about the missing permission.

## Response format

All responses are JSON.

**Success**

| Status | Meaning |
|--------|---------|
| `200 OK` | Request successful |
| `201 Created` | Resource created |
| `204 No Content` | Success with no response body |

**Errors**

| Status | Meaning |
|--------|---------|
| `400 Bad Request` | Invalid request data |
| `401 Unauthorized` | Missing or invalid API key |
| `403 Forbidden` | Insufficient permissions |
| `404 Not Found` | Resource not found |

Error bodies typically include an `error` field with a descriptive message.

---

## Devices

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/devices` | `view_devices` | List all devices (includes IP addresses, tags, custom fields) |
| GET | `/api/v1/devices/{id}` | `view_device` | Get device details |
| GET | `/api/v1/devices/by-tag/{tag}` | `view_devices` | List devices by tag name or ID. Use `?format=simple` for `{device, ip}` pairs |
| POST | `/api/v1/devices` | `add_device` | Create device |
| PUT | `/api/v1/devices/{id}` | `edit_device` | Update device |
| DELETE | `/api/v1/devices/{id}` | `delete_device` | Delete device |
| POST | `/api/v1/devices/{id}/ips` | `add_device_ip` | Assign IP to device |
| DELETE | `/api/v1/devices/{id}/ips/{ip_id}` | `remove_device_ip` | Remove IP from device |

**Create device** (`POST /api/v1/devices`)

```json
{
  "name": "server-01",
  "description": "Optional description",
  "device_type_id": 1
}
```

**Update device** (`PUT /api/v1/devices/{id}`) — include only fields to change: `name`, `description`, `device_type_id`.

**Add IP** (`POST /api/v1/devices/{id}/ips`)

```json
{
  "ip_id": 42
}
```

---

## Subnets

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/subnets` | `view_subnet` | List all subnets |
| GET | `/api/v1/subnets/{id}` | `view_subnet` | Get subnet details |
| GET | `/api/v1/subnets/{id}/next_free_ip` | `view_subnet` | Get next available IP |
| POST | `/api/v1/subnets` | `add_subnet` | Create subnet |
| PUT | `/api/v1/subnets/{id}` | `edit_subnet` | Update subnet |
| DELETE | `/api/v1/subnets/{id}` | `delete_subnet` | Delete subnet |

**Create subnet** (`POST /api/v1/subnets`)

```json
{
  "name": "Office LAN",
  "cidr": "192.168.1.0/24",
  "site": "HQ",
  "vlan_id": 100,
  "vlan_description": "Optional",
  "vlan_notes": "Optional"
}
```

Subnets must be `/24` or smaller (prefix length ≥ 24).

---

## DHCP

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/subnets/{id}/dhcp` | `view_dhcp` | Get DHCP pool configuration |
| POST | `/api/v1/subnets/{id}/dhcp` | `configure_dhcp` | Create or update DHCP pool |

**Configure pool** (`POST /api/v1/subnets/{id}/dhcp`)

```json
{
  "pools": [
    {
      "start_ip": "192.168.1.10",
      "end_ip": "192.168.1.200",
      "excluded_ips": ["192.168.1.1", "192.168.1.254"]
    }
  ]
}
```

**Remove pool**

```json
{
  "remove": true
}
```

---

## Racks

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/racks` | `view_racks` | List all racks |
| GET | `/api/v1/racks/{id}` | `view_rack` | Get rack details |
| POST | `/api/v1/racks` | `add_rack` | Create rack |
| DELETE | `/api/v1/racks/{id}` | `delete_rack` | Delete rack |
| POST | `/api/v1/racks/{id}/devices` | `add_device_to_rack` | Add device to rack position |
| DELETE | `/api/v1/racks/{id}/devices/{rack_device_id}` | `remove_device_from_rack` | Remove device from rack |

---

## Tags

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/tags` | `view_tags` | List all tags |
| GET | `/api/v1/tags?format=simple` | `view_tags` | List tags in simple format |
| GET | `/api/v1/tags/{id}` | `view_tags` | Get tag details |
| POST | `/api/v1/tags` | `add_tag` | Create tag |
| PUT | `/api/v1/tags/{id}` | `edit_tag` | Update tag |
| DELETE | `/api/v1/tags/{id}` | `delete_tag` | Delete tag |
| GET | `/api/v1/devices/{id}/tags` | `view_device` | Get tags for a device |
| POST | `/api/v1/devices/{id}/tags` | `assign_device_tag` | Assign tag to device |
| DELETE | `/api/v1/devices/{id}/tags/{tag_id}` | `remove_device_tag` | Remove tag from device |

**Assign tag** (`POST /api/v1/devices/{id}/tags`)

```json
{
  "tag_id": 3
}
```

---

## Custom fields

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/custom_fields/{entity_type}` | `view_custom_fields` | List field definitions (`device` or `subnet`) |
| POST | `/api/v1/custom_fields` | `manage_custom_fields` | Create field definition |
| PUT | `/api/v1/custom_fields/{id}` | `manage_custom_fields` | Update field definition |
| DELETE | `/api/v1/custom_fields/{id}` | `manage_custom_fields` | Delete field definition |

**Create field** (`POST /api/v1/custom_fields`)

```json
{
  "entity_type": "device",
  "name": "Asset tag",
  "field_key": "asset_tag",
  "field_type": "text",
  "required": false,
  "default_value": "",
  "help_text": "Optional help text",
  "display_order": 0,
  "validation_rules": {
    "max_length": 32
  }
}
```

---

## System & admin

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/v1/info` | *(authenticated)* | API version (`2.0`) and current user info |
| GET | `/api/v1/device-types` | `view_device_types` | List device types |
| GET | `/api/v1/devices/{id}/ip_history` | `view_device` | IP assignment history for a device |
| GET | `/api/v1/ips/{ip}/history` | `view_subnet` | IP assignment history for an address |
| GET | `/api/v1/audit` | `view_audit` | List audit log entries (`limit`, `offset` query params) |
| GET | `/api/v1/users` | `view_users` | List users |
| GET | `/api/v1/roles` | `view_users` | List roles with permissions |

Mutating API calls (`POST`, `PUT`, `DELETE`, `PATCH`) are logged to the audit log as `api_usage`. GET requests are not audited (v2 change — see [v1-to-v2-breaking-changes.md](v1-to-v2-breaking-changes.md)).

---

## Example

```bash
curl -H "X-API-Key: YOUR_KEY" https://your-ipam-host/api/v1/devices

curl -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "switch-01", "description": "Core switch"}' \
  https://your-ipam-host/api/v1/devices
```
