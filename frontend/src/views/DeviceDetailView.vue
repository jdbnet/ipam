<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { api, type Device, type Tag, type Subnet } from "@/api";
import type { IpHistoryEntry } from "@/components/IpHistoryModal.vue";
import CustomFieldValues from "@/components/CustomFieldValues.vue";
import { useAuthStore } from "@/stores/auth";
import { formatLocalTime } from "@/utils/datetime";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const device = ref<Device | null>(null);
const allTags = ref<Tag[]>([]);
const subnets = ref<Subnet[]>([]);
const availableIps = ref<{ id: number; ip: string }[]>([]);
const history = ref<IpHistoryEntry[]>([]);
const editName = ref("");
const editDescription = ref("");
const saving = ref(false);
const loading = ref(true);
const error = ref("");
const showAssignIp = ref(false);
const assignForm = ref({ site: "", subnet_id: 0, ip_id: 0 });
const err = ref("");

const sites = computed(() => {
  const list = [...new Set(subnets.value.map((s) => s.site || "Unassigned"))];
  return list.sort((a, b) => {
    if (a === "Unassigned") return -1;
    if (b === "Unassigned") return 1;
    return a.localeCompare(b);
  });
});

const deviceSites = computed(() =>
  [...new Set((device.value?.ip_addresses ?? []).map((ip) => ip.site || "Unassigned"))],
);

const assignableSites = computed(() =>
  deviceSites.value.length ? sites.value.filter((s) => deviceSites.value.includes(s)) : sites.value,
);

const subnetsForSite = computed(() =>
  subnets.value.filter((s) => (s.site || "Unassigned") === assignForm.value.site),
);

async function loadDevice() {
  loading.value = true;
  error.value = "";
  try {
    const id = Number(route.params.id);
    const [d, tags, h, sn] = await Promise.all([
      api.device(id),
      api.tags(),
      api.deviceIpHistory(id).catch(() => []),
      api.subnets(false),
    ]);
    device.value = d;
    editName.value = d.name;
    editDescription.value = d.description || "";
    allTags.value = tags;
    subnets.value = sn;
    history.value = h as IpHistoryEntry[];
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load device";
    device.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(loadDevice);

async function loadAvailableIps(subnetId: number) {
  if (!subnetId) {
    availableIps.value = [];
    assignForm.value.ip_id = 0;
    return;
  }
  availableIps.value = await api.availableIps(subnetId);
  assignForm.value.ip_id = availableIps.value[0]?.id ?? 0;
}

async function onSiteChange() {
  const list = subnetsForSite.value;
  assignForm.value.subnet_id = list[0]?.id ?? 0;
  await loadAvailableIps(assignForm.value.subnet_id);
}

async function onSubnetChange() {
  await loadAvailableIps(assignForm.value.subnet_id);
}

async function openAssignIpModal() {
  err.value = "";
  const defaultSite = assignableSites.value[0] ?? sites.value[0] ?? "";
  const defaultSubnet = subnets.value.find((s) => (s.site || "Unassigned") === defaultSite) ?? subnets.value[0];
  assignForm.value = {
    site: defaultSite,
    subnet_id: defaultSubnet?.id ?? 0,
    ip_id: 0,
  };
  if (assignForm.value.subnet_id) await loadAvailableIps(assignForm.value.subnet_id);
  showAssignIp.value = true;
}

async function saveDevice() {
  if (!device.value) return;
  saving.value = true;
  err.value = "";
  try {
    await api.updateDevice(device.value.id, { name: editName.value, description: editDescription.value });
    device.value.name = editName.value;
    device.value.description = editDescription.value;
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to save";
  } finally {
    saving.value = false;
  }
}

async function assignTag(tagId: number) {
  if (!device.value || !tagId) return;
  await api.assignTag(device.value.id, tagId);
  device.value = await api.device(device.value.id);
}

async function removeTag(tagId: number) {
  if (!device.value || !confirm("Remove this tag?")) return;
  await api.removeTag(device.value.id, tagId);
  device.value = await api.device(device.value.id);
}

async function assignIp() {
  if (!device.value || !assignForm.value.ip_id) return;
  err.value = "";
  try {
    await api.assignIp(device.value.id, assignForm.value.ip_id);
    showAssignIp.value = false;
    await loadDevice();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function removeIp(ipId: number) {
  if (!device.value || !confirm("Remove this IP from the device?")) return;
  await api.removeIp(device.value.id, ipId);
  await loadDevice();
}

async function deleteDevice() {
  if (!device.value || !confirm(`Delete device "${device.value.name}"? This cannot be undone.`)) return;
  await api.deleteDevice(device.value.id);
  router.push("/devices");
}

function onCustomFieldsSaved(values: Record<string, unknown>) {
  if (device.value) device.value.custom_fields = values;
}

function formatTime(ts?: string) {
  return formatLocalTime(ts, "Unknown");
}
</script>
<template>
  <div>
    <RouterLink to="/devices" class="text-sm text-accent hover:underline">← Devices</RouterLink>
    <p v-if="loading" class="mt-8 text-slate-500">Loading…</p>
    <p v-else-if="error" class="mt-8 text-red-500">{{ error }}</p>
    <template v-else-if="device">
      <div class="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div class="flex min-w-0 max-w-2xl flex-1 flex-col gap-2">
          <template v-if="auth.can('edit_device')">
            <input
              v-model="editName"
              class="input-field block w-full border-0 bg-transparent px-0 py-0 text-2xl font-bold shadow-none focus:ring-0"
              aria-label="Device name"
              @blur="saveDevice"
            />
            <textarea
              v-model="editDescription"
              class="input-field block w-full resize-y text-sm"
              placeholder="Add a description…"
              rows="2"
              @blur="saveDevice"
            />
          </template>
          <template v-else>
            <h1 class="text-2xl font-bold">{{ device.name }}</h1>
            <p v-if="device.description" class="text-slate-500">{{ device.description }}</p>
          </template>
          <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        </div>
        <button
          v-if="auth.can('delete_device')"
          class="shrink-0 text-sm text-red-500 hover:underline"
          @click="deleteDevice"
        >Delete device</button>
      </div>
      <div class="mt-6 grid gap-4 lg:grid-cols-2">
        <div class="card">
          <div class="flex items-center justify-between">
            <h2 class="font-semibold">IP addresses</h2>
            <button v-if="auth.can('add_device_ip')" class="text-sm text-accent hover:underline" @click="openAssignIpModal">Assign IP</button>
          </div>
          <ul class="mt-3 space-y-2">
            <li v-for="ip in device.ip_addresses" :key="ip.id" class="flex items-center justify-between gap-3 font-mono text-sm">
              <span class="min-w-0">
                {{ ip.ip }}
                <span v-if="ip.notes || ip.subnet_name" class="font-sans text-slate-500">
                  {{ ip.notes || ip.subnet_name }}
                </span>
              </span>
              <button v-if="auth.can('remove_device_ip')" class="text-red-500 hover:underline" @click="removeIp(ip.id)">Remove</button>
            </li>
            <li v-if="!device.ip_addresses?.length" class="text-sm text-slate-500">None assigned</li>
          </ul>
        </div>
        <div class="card">
          <h2 class="font-semibold">Tags</h2>
          <div class="mt-2 flex flex-wrap gap-2">
            <span v-for="t in device.tags" :key="t.id" class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs" :style="{ backgroundColor: (t.color || '#6B7280') + '33' }">
              {{ t.name }}
              <button v-if="auth.can('assign_device_tag')" class="text-red-500 hover:underline" @click="removeTag(t.id)">×</button>
            </span>
            <span v-if="!device.tags?.length" class="text-sm text-slate-500">No tags</span>
          </div>
          <select v-if="auth.can('assign_device_tag')" class="input-field mt-3" @change="assignTag(Number(($event.target as HTMLSelectElement).value)); ($event.target as HTMLSelectElement).value = ''">
            <option value="">Add tag…</option>
            <option v-for="t in allTags.filter((t) => !device!.tags?.some((dt) => dt.id === t.id))" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
        <CustomFieldValues
          v-if="auth.can('view_custom_fields')"
          class="lg:col-span-2"
          entity-type="device"
          :entity-id="device.id"
          :values="device.custom_fields"
          :can-edit="auth.can('edit_device')"
          @saved="onCustomFieldsSaved"
        />
        <div class="card lg:col-span-2">
          <h2 class="font-semibold">IP history</h2>
          <p v-if="!history.length" class="mt-2 text-sm text-slate-500">No assignment history.</p>
          <ul v-else class="mt-3 space-y-3">
            <li v-for="(entry, i) in history" :key="i" class="flex gap-3 text-sm">
              <span class="shrink-0 text-xs font-semibold uppercase" :class="entry.action === 'assigned' ? 'text-emerald-600' : 'text-red-500'">
                {{ entry.action === "assigned" ? "Assigned" : "Removed" }}
              </span>
              <span class="font-mono">{{ entry.ip }}</span>
              <span class="text-slate-500">· {{ entry.user_name }} · {{ formatTime(entry.timestamp) }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div v-if="showAssignIp" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAssignIp = false">
        <form class="card w-full max-w-md space-y-3" @submit.prevent="assignIp">
          <h2 class="text-lg font-semibold">Assign IP</h2>
          <select v-if="!deviceSites.length" v-model="assignForm.site" class="input-field" @change="onSiteChange">
            <option v-for="site in assignableSites" :key="site" :value="site">{{ site }}</option>
          </select>
          <select v-model="assignForm.subnet_id" class="input-field" @change="onSubnetChange">
            <option v-for="s in subnetsForSite" :key="s.id" :value="s.id">{{ s.name }} ({{ s.cidr }})</option>
          </select>
          <select v-model="assignForm.ip_id" class="input-field" required>
            <option v-for="ip in availableIps" :key="ip.id" :value="ip.id">{{ ip.ip }}</option>
          </select>
          <p v-if="assignForm.subnet_id && !availableIps.length" class="text-sm text-slate-500">No available IPs in this subnet</p>
          <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
          <div class="flex gap-2">
            <button type="submit" class="btn-primary" :disabled="!assignForm.ip_id">Assign</button>
            <button type="button" class="btn-secondary" @click="showAssignIp = false">Cancel</button>
          </div>
        </form>
      </div>
    </template>
  </div>
</template>
