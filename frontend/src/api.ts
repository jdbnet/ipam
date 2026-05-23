const jsonHeaders = { "Content-Type": "application/json" };

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) throw new Error("unauthorized");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { error?: string }).error || res.statusText);
  return data as T;
}

function fetchApi(path: string, init?: RequestInit) {
  return fetch(path, { credentials: "include", ...init });
}

export interface MeResponse {
  logged_in: boolean;
  app_version?: string;
  org?: { name: string; logo: string };
  user?: { id: number; name: string; email: string };
  permissions?: string[];
}

export interface Device {
  id: number;
  name: string;
  description?: string;
  ip_addresses?: IpOnDevice[];
  tags?: Tag[];
  custom_fields?: Record<string, unknown>;
}

export interface IpOnDevice {
  id: number;
  ip: string;
  hostname?: string;
  subnet_id?: number;
  subnet_name?: string;
  cidr?: string;
  site?: string;
}

export interface Subnet {
  id: number;
  name: string;
  cidr: string;
  site?: string;
  vlan_id?: number;
  vlan_description?: string;
  vlan_notes?: string;
  utilization?: number;
  total_ips?: number;
  used_ips?: number;
  custom_fields?: Record<string, unknown>;
  ip_addresses?: SubnetIp[];
}

export interface SubnetIp {
  id: number;
  ip: string;
  hostname?: string;
  device_id?: number;
  device_name?: string;
  notes?: string;
}

export interface Tag {
  id: number;
  name: string;
  color?: string;
  description?: string;
}

export interface Rack {
  id: number;
  name: string;
  site: string;
  height_u: number;
  used_u?: number;
  percent_full?: number;
  devices?: RackDevice[];
  site_devices?: { id: number; name: string; description?: string }[];
}

export interface RackDevice {
  id: number;
  position_u: number;
  side: string;
  device_id?: number;
  device_name?: string;
  nonnet_device_name?: string;
}

export interface AuditEntry {
  id: number;
  user_name?: string;
  action: string;
  details?: string;
  timestamp?: string;
}

export interface UserRow {
  id: number;
  name: string;
  email: string;
  role_id?: number;
  role_name?: string;
}

export interface RoleRow {
  id: number;
  name: string;
  description?: string;
  require_2fa?: boolean;
  permissions?: { id: number; name: string; category?: string }[];
}

export interface CustomFieldDef {
  id: number;
  entity_type: string;
  name: string;
  field_key: string;
  field_type: string;
  required?: boolean;
  display_order?: number;
}

export const api = {
  async me(): Promise<MeResponse> {
    return handle(await fetchApi("/api/v2/auth/me"));
  },
  async login(email: string, password: string) {
    return handle<{ ok?: boolean; requires_2fa?: boolean; requires_setup?: boolean }>(
      await fetchApi("/api/v2/auth/login", {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ email, password }),
      }),
    );
  },
  async verify2fa(code: string, useBackup = false) {
    return handle(await fetchApi("/api/v2/auth/verify-2fa", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ code, use_backup: useBackup }),
    }));
  },
  async setup2fa(action: "generate" | "verify", code?: string) {
    return handle<{ secret?: string; qr_code?: string; backup_codes?: string[] }>(
      await fetchApi("/api/v2/auth/setup-2fa", {
        method: "POST",
        headers: jsonHeaders,
        body: JSON.stringify({ action, code }),
      }),
    );
  },
  async logout() {
    return handle(await fetchApi("/api/v2/auth/logout", { method: "POST" }));
  },
  async dashboard() {
    return handle<{ sites: Record<string, Subnet[]> }>(await fetchApi("/api/v2/dashboard"));
  },
  async search(q: string) {
    return handle<Record<string, unknown[]>>(await fetchApi(`/api/v2/search?q=${encodeURIComponent(q)}`));
  },
  async devices(params?: { tag?: string; site?: string }) {
    const p = new URLSearchParams();
    if (params?.tag) p.set("tag", params.tag);
    if (params?.site) p.set("site", params.site);
    const q = p.toString();
    const d = await handle<{ items: Device[] }>(await fetchApi(`/api/v2/devices${q ? `?${q}` : ""}`));
    return d.items;
  },
  async device(id: number) {
    return handle<Device>(await fetchApi(`/api/v2/devices/${id}`));
  },
  async createDevice(body: Partial<Device>) {
    return handle(await fetchApi("/api/v2/devices", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async updateDevice(id: number, body: Partial<Device>) {
    return handle(await fetchApi(`/api/v2/devices/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteDevice(id: number) {
    return handle(await fetchApi(`/api/v2/devices/${id}`, { method: "DELETE" }));
  },
  async assignIp(deviceId: number, ipId: number) {
    return handle(await fetchApi(`/api/v2/devices/${deviceId}/ips`, {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ ip_id: ipId }),
    }));
  },
  async removeIp(deviceId: number, ipId: number) {
    return handle(await fetchApi(`/api/v2/devices/${deviceId}/ips/${ipId}`, { method: "DELETE" }));
  },
  async deviceIpHistory(deviceId: number) {
    const d = await handle<{ items: unknown[] }>(await fetchApi(`/api/v2/devices/${deviceId}/ip-history`));
    return d.items;
  },
  async subnets(includeUtil = true) {
    const d = await handle<{ items: Subnet[] }>(
      await fetchApi(`/api/v2/subnets${includeUtil ? "?include=utilization" : ""}`),
    );
    return d.items;
  },
  async subnet(id: number) {
    return handle<Subnet>(await fetchApi(`/api/v2/subnets/${id}`));
  },
  async createSubnet(body: Partial<Subnet>) {
    return handle(await fetchApi("/api/v2/subnets", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async updateSubnet(id: number, body: Partial<Subnet>) {
    return handle(await fetchApi(`/api/v2/subnets/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteSubnet(id: number) {
    return handle(await fetchApi(`/api/v2/subnets/${id}`, { method: "DELETE" }));
  },
  async availableIps(subnetId: number) {
    const d = await handle<{ items: { id: number; ip: string }[] }>(await fetchApi(`/api/v2/subnets/${subnetId}/available-ips`));
    return d.items;
  },
  async patchIpNotes(ipId: number, notes: string) {
    return handle(await fetchApi(`/api/v2/ip-addresses/${ipId}`, {
      method: "PATCH", headers: jsonHeaders, body: JSON.stringify({ notes }),
    }));
  },
  async ipHistory(ip: string) {
    const d = await handle<{ items: unknown[] }>(await fetchApi(`/api/v2/ips/${encodeURIComponent(ip)}/history`));
    return d.items;
  },
  subnetExportUrl(id: number) {
    return `/api/v2/subnets/${id}/export`;
  },
  async tags() {
    const d = await handle<{ tags?: Tag[]; items?: Tag[] }>(await fetchApi("/api/v2/tags"));
    return d.items ?? d.tags ?? [];
  },
  async createTag(body: Partial<Tag>) {
    return handle(await fetchApi("/api/v2/tags", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async updateTag(id: number, body: Partial<Tag>) {
    return handle(await fetchApi(`/api/v2/tags/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteTag(id: number) {
    return handle(await fetchApi(`/api/v2/tags/${id}`, { method: "DELETE" }));
  },
  async assignTag(deviceId: number, tagId: number) {
    return handle(await fetchApi(`/api/v2/devices/${deviceId}/tags`, {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ tag_id: tagId }),
    }));
  },
  async removeTag(deviceId: number, tagId: number) {
    return handle(await fetchApi(`/api/v2/devices/${deviceId}/tags/${tagId}`, { method: "DELETE" }));
  },
  async racks() {
    const d = await handle<{ racks?: Rack[]; items?: Rack[] }>(await fetchApi("/api/v2/racks"));
    return d.racks ?? d.items ?? [];
  },
  async rack(id: number) {
    return handle<Rack>(await fetchApi(`/api/v2/racks/${id}`));
  },
  async createRack(body: Partial<Rack>) {
    return handle(await fetchApi("/api/v2/racks", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteRack(id: number) {
    return handle(await fetchApi(`/api/v2/racks/${id}`, { method: "DELETE" }));
  },
  async updateRack(id: number, body: Partial<Rack>) {
    return handle(await fetchApi(`/api/v2/racks/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async addRackDevice(rackId: number, body: { position_u: number; side: string; device_id?: number; nonnet_device_name?: string }) {
    return handle(await fetchApi(`/api/v2/racks/${rackId}/devices`, { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async removeRackDevice(rackId: number, rackDeviceId: number) {
    return handle(await fetchApi(`/api/v2/racks/${rackId}/devices/${rackDeviceId}`, { method: "DELETE" }));
  },
  rackExportUrl(id: number) {
    return `/api/v2/racks/${id}/export`;
  },
  async createCustomField(body: Record<string, unknown>) {
    return handle(await fetchApi("/api/v2/custom_fields", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async updateCustomField(id: number, body: Record<string, unknown>) {
    return handle(await fetchApi(`/api/v2/custom_fields/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteCustomField(id: number) {
    return handle(await fetchApi(`/api/v2/custom_fields/${id}`, { method: "DELETE" }));
  },
  async reorderCustomFields(entityType: string, fieldOrders: Record<number, number>) {
    return handle(await fetchApi("/api/v2/custom-fields/reorder", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ entity_type: entityType, field_orders: fieldOrders }),
    }));
  },
  async createUser(body: { name: string; email: string; password: string; role_id?: number }) {
    return handle(await fetchApi("/api/v2/users", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async updateUser(id: number, body: Record<string, unknown>) {
    return handle(await fetchApi(`/api/v2/users/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteUser(id: number) {
    return handle(await fetchApi(`/api/v2/users/${id}`, { method: "DELETE" }));
  },
  async regenerateApiKey(userId: number) {
    return handle<{ api_key: string }>(await fetchApi(`/api/v2/users/${userId}/regenerate-api-key`, { method: "POST" }));
  },
  async createRole(body: { name: string; description?: string; permission_ids?: number[]; require_2fa?: boolean }) {
    return handle(await fetchApi("/api/v2/roles", { method: "POST", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async updateRole(id: number, body: Record<string, unknown>) {
    return handle(await fetchApi(`/api/v2/roles/${id}`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify(body) }));
  },
  async deleteRole(id: number) {
    return handle(await fetchApi(`/api/v2/roles/${id}`, { method: "DELETE" }));
  },
  async disable2fa(password: string) {
    return handle(await fetchApi("/api/v2/account/disable-2fa", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ password }),
    }));
  },
  async regenerateBackupCodes(password: string) {
    return handle<{ backup_codes: string[] }>(await fetchApi("/api/v2/account/regenerate-backup-codes", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ password }),
    }));
  },
  async audit(limit = 100) {
    const d = await handle<{ logs: AuditEntry[] }>(await fetchApi(`/api/v2/audit?limit=${limit}`));
    return d.logs;
  },
  auditExportUrl: "/api/v2/audit/export",
  async users() {
    const d = await handle<{ users?: UserRow[]; items?: UserRow[] }>(await fetchApi("/api/v2/users"));
    return d.users ?? d.items ?? [];
  },
  async roles() {
    const d = await handle<{ roles?: RoleRow[] }>(await fetchApi("/api/v2/roles"));
    return d.roles ?? [];
  },
  async permissions() {
    const d = await handle<{ items: { id: number; name: string; category?: string }[] }>(
      await fetchApi("/api/v2/permissions"),
    );
    return d.items;
  },
  async customFields(entityType: string) {
    const d = await handle<{ fields?: CustomFieldDef[] }>(await fetchApi(`/api/v2/custom_fields/${entityType}`));
    return d.fields ?? [];
  },
  async bulkAssignIps(deviceId: number, ipIds: number[]) {
    return handle(await fetchApi("/api/v2/bulk/assign-ips", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ device_id: deviceId, ip_ids: ipIds }),
    }));
  },
  async bulkCreateDevices(names: string[]) {
    return handle(await fetchApi("/api/v2/bulk/create-devices", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ names }),
    }));
  },
  async bulkAssignTags(deviceIds: number[], tagId: number) {
    return handle(await fetchApi("/api/v2/bulk/assign-tags", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ device_ids: deviceIds, tag_id: tagId }),
    }));
  },
  async account() {
    return handle(await fetchApi("/api/v2/account"));
  },
  async changePassword(current: string, newPw: string) {
    return handle(await fetchApi("/api/v2/account/change-password", {
      method: "POST", headers: jsonHeaders, body: JSON.stringify({ current_password: current, new_password: newPw }),
    }));
  },
  async getDhcp(subnetId: number) {
    return handle(await fetchApi(`/api/v2/subnets/${subnetId}/dhcp`));
  },
  async setDhcp(subnetId: number, body: unknown) {
    return handle(await fetchApi(`/api/v2/subnets/${subnetId}/dhcp`, {
      method: "POST", headers: jsonHeaders, body: JSON.stringify(body),
    }));
  },
};
