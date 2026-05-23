<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { api, type Device, type Tag, type Subnet } from "@/api";
import type { IpHistoryEntry } from "@/components/IpHistoryModal.vue";
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
const saving = ref(false);
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

onMounted(async () => {
  const id = Number(route.params.id);
  const [d, tags, h, sn] = await Promise.all([
    api.device(id),
    api.tags(),
    api.deviceIpHistory(id).catch(() => []),
    api.subnets(false),
  ]);
  device.value = d;
  editName.value = d.name;
  allTags.value = tags;
  subnets.value = sn;
  history.value = h as IpHistoryEntry[];
});

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

async function saveName() {
  if (!device.value) return;
  saving.value = true;
  await api.updateDevice(device.value.id, { name: editName.value });
  device.value.name = editName.value;
  saving.value = false;
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
    device.value = await api.device(device.value.id);
    history.value = (await api.deviceIpHistory(device.value.id)) as IpHistoryEntry[];
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function removeIp(ipId: number) {
  if (!device.value || !confirm("Remove this IP from the device?")) return;
  await api.removeIp(device.value.id, ipId);
  device.value = await api.device(device.value.id);
  history.value = (await api.deviceIpHistory(device.value.id)) as IpHistoryEntry[];
}

async function deleteDevice() {
  if (!device.value || !confirm(`Delete device "${device.value.name}"? This cannot be undone.`)) return;
  await api.deleteDevice(device.value.id);
  router.push("/devices");
}

function formatTime(ts?: string) {
  return formatLocalTime(ts, "Unknown");
}
</script>
<template>
  <div v-if="device">
    <RouterLink to="/devices" class="text-sm text-accent hover:underline">← Devices</RouterLink>
    <div class="mt-4 flex flex-wrap items-start justify-between gap-4">
      <div class="flex-1">
        <input v-if="auth.can('edit_device')" v-model="editName" class="input-field max-w-md text-xl font-bold" @blur="saveName" />
        <h1 v-else class="text-2xl font-bold">{{ device.name }}</h1>
        <p class="mt-1 text-slate-500">{{ device.description || "No description" }}</p>
      </div>
      <button
        v-if="auth.can('delete_device')"
        class="text-sm text-red-500 hover:underline"
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
          <li v-for="ip in device.ip_addresses" :key="ip.id" class="flex items-center justify-between font-mono text-sm">
            <span>{{ ip.ip }} <span class="text-slate-500">({{ ip.subnet_name }})</span></span>
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
        </div>
        <select v-if="auth.can('assign_device_tag')" class="input-field mt-3" @change="assignTag(Number(($event.target as HTMLSelectElement).value)); ($event.target as HTMLSelectElement).value = ''">
          <option value="">Add tag…</option>
          <option v-for="t in allTags.filter((t) => !device!.tags?.some((dt) => dt.id === t.id))" :key="t.id" :value="t.id">{{ t.name }}</option>
        </select>
      </div>
      <div class="card lg:col-span-2">
        <h2 class="font-semibold">IP history</h2>
        <p v-if="!history.length" class="mt-2 text-sm text-slate-500">No assignment history.</p>
        <ul v-else class="mt-3 space-y-3">
          <li v-for="(entry, i) in history" :key="i" class="flex gap-3 text-sm">
            <span class="shrink-0 font-semibold uppercase text-xs" :class="entry.action === 'assigned' ? 'text-emerald-600' : 'text-red-500'">
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
  </div>
</template>
