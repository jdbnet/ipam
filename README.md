<div align="center">
  <img src="https://assets.jdbnet.co.uk/projects/ipam.png" alt="IPAM" width="200" />

  # IP Address Management
</div>

A Flask-based web application for IP Address Management (IPAM). Manage subnets, IP addresses, devices, DHCP pools, and rack infrastructure through a Vue 3 web interface and a JSON REST API.

## Features

- **Subnet management** - CIDR subnets with automatic IP generation
- **IP assignment** - Assign addresses to devices with hostname tracking
- **Device management** - Names, descriptions, tags, and custom fields
- **DHCP pools** — Configure ranges and excluded IPs per subnet
- **Rack management** - U positions with front/back layout
- **Site organisation** - Group subnets and devices by location
- **Audit logging** - Filterable change history with CSV export
- **Role-based access control** - Granular permissions and custom roles
- **REST API v2** - Session cookies for the browser, API keys for automation

## Screenshot

![IPAM Dashboard](img/screenshot.png)

## Docker Compose

```yaml
services:
  ipam:
    image: cr.jdbnet.co.uk/public/ipam:latest
    container_name: ipam
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      - MYSQL_HOST=10.10.2.27
      - MYSQL_USER=ipam
      - MYSQL_PASSWORD=your_password
      - MYSQL_DATABASE=ipam
      - SECRET_KEY=your_secret_key
      - NAME=Your Organisation
      - LOGO_PNG=https://example.com/logo.png
```
