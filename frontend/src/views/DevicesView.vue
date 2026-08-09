<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { RouterLink } from "vue-router";
import { api, type Device, type Subnet } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const devices = ref<Device[]>([]);
const tagFilter = ref("");
const tags = ref<string[]>([]);
const subnets = ref<Subnet[]>([]);
const availableIps = ref<{ id: number; ip: string }[]>([]);
const loading = ref(true);

const showAdd = ref(false);
const showBulk = ref(false);
const assignIpOnCreate = ref(false);
const addForm = ref({ name: "", description: "", site: "", subnet_id: 0, ip_id: 0 });
const bulkForm = ref({ names: "" });
const err = ref("");

const sites = computed(() =>
  [...new Set(subnets.value.map((s) => s.site || "Unassigned"))].sort(),
);

const subnetsForSite = computed(() =>
  subnets.value.filter((s) => (s.site || "Unassigned") === addForm.value.site),
);

const bySite = computed(() => {
  const m: Record<string, Device[]> = {};
  for (const d of devices.value) {
    const site = d.ip_addresses?.[0]?.site || "Unassigned";
    if (!m[site]) m[site] = [];
    m[site].push(d);
  }
  return m;
});

const siteOrder = computed(() =>
  Object.keys(bySite.value).sort((a, b) => {
    if (a === "Unassigned") return -1;
    if (b === "Unassigned") return 1;
    return a.localeCompare(b);
  }),
);

async function loadDevices() {
  loading.value = true;
  devices.value = await api.devices({ tag: tagFilter.value || undefined });
  loading.value = false;
}

onMounted(async () => {
  const [tagList, subnetData] = await Promise.all([api.tags(), api.subnets(false)]);
  tags.value = tagList.map((t) => t.name);
  subnets.value = subnetData.items;
  if (subnetData.items.length) {
    addForm.value.site = subnetData.items[0].site || "Unassigned";
    addForm.value.subnet_id = subnetData.items[0].id;
  }
  await loadDevices();
});

async function loadAvailableIps(subnetId: number) {
  if (!subnetId) {
    availableIps.value = [];
    addForm.value.ip_id = 0;
    return;
  }
  availableIps.value = await api.availableIps(subnetId);
  addForm.value.ip_id = availableIps.value[0]?.id ?? 0;
}

async function onAddSiteChange() {
  const list = subnetsForSite.value;
  addForm.value.subnet_id = list[0]?.id ?? 0;
  await loadAvailableIps(addForm.value.subnet_id);
}

async function onAddSubnetChange() {
  await loadAvailableIps(addForm.value.subnet_id);
}

async function onAssignIpToggle() {
  if (assignIpOnCreate.value) {
    if (!addForm.value.site) addForm.value.site = sites.value[0] ?? "";
    await onAddSiteChange();
  } else {
    availableIps.value = [];
    addForm.value.ip_id = 0;
  }
}

async function openAddModal() {
  err.value = "";
  assignIpOnCreate.value = false;
  availableIps.value = [];
  const defaultSite = sites.value[0] ?? "";
  const defaultSubnet = subnets.value.find((s) => (s.site || "Unassigned") === defaultSite) ?? subnets.value[0];
  addForm.value = {
    name: "",
    description: "",
    site: defaultSite,
    subnet_id: defaultSubnet?.id ?? 0,
    ip_id: 0,
  };
  showAdd.value = true;
}

async function filterTag(t: string) {
  tagFilter.value = t;
  await loadDevices();
}

async function createDevice() {
  err.value = "";
  try {
    const created = await api.createDevice({
      name: addForm.value.name,
      description: addForm.value.description,
    }) as { id: number };
    if (assignIpOnCreate.value) {
      if (!addForm.value.ip_id) {
        err.value = "Select an IP address or uncheck “Assign an IP address”";
        return;
      }
      if (auth.can("add_device_ip")) {
        await api.assignIp(created.id, addForm.value.ip_id);
      }
    }
    showAdd.value = false;
    assignIpOnCreate.value = false;
    availableIps.value = [];
    addForm.value = {
      name: "",
      description: "",
      site: sites.value[0] ?? "",
      subnet_id: subnets.value[0]?.id ?? 0,
      ip_id: 0,
    };
    await loadDevices();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function bulkCreate() {
  err.value = "";
  const names = bulkForm.value.names.split("\n").map((n) => n.trim()).filter(Boolean);
  if (!names.length) {
    err.value = "Enter at least one device name";
    return;
  }
  try {
    await api.bulkCreateDevices(names);
    showBulk.value = false;
    bulkForm.value.names = "";
    await loadDevices();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}
</script>
<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-2xl font-bold">Devices</h1>
      <div v-if="auth.can('add_device')" class="flex gap-2">
        <button class="btn-primary text-sm" @click="openAddModal">Add device</button>
        <button class="btn-secondary text-sm" @click="showBulk = true; err = ''">Bulk add</button>
      </div>
    </div>
    <div class="mt-4 flex flex-wrap gap-2">
      <button class="rounded-full px-3 py-1 text-xs" :class="!tagFilter ? 'bg-accent text-slate-950' : 'bg-surface-overlay'" @click="filterTag('')">All</button>
      <button v-for="t in tags" :key="t" class="rounded-full px-3 py-1 text-xs" :class="tagFilter === t ? 'bg-accent text-slate-950' : 'bg-surface-overlay'" @click="filterTag(t)">{{ t }}</button>
    </div>
    <div v-if="loading" class="mt-8 text-slate-500">Loading…</div>
    <div v-else class="mt-6 space-y-6">
      <section v-for="site in siteOrder" :key="site">
        <h2 class="mb-2 font-semibold text-accent">{{ site }}</h2>
        <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <RouterLink v-for="d in bySite[site]" :key="d.id" :to="`/devices/${d.id}`" class="card flex items-center gap-3 py-3 transition hover:border-accent/50">
            <div class="min-w-0 flex-1">
              <div class="truncate font-medium">{{ d.name }}</div>
              <div class="truncate text-xs text-slate-500">{{ d.ip_addresses?.map((i) => i.ip).join(", ") || "No IPs" }}</div>
            </div>
          </RouterLink>
        </div>
      </section>
    </div>

    <div v-if="showAdd" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAdd = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="createDevice">
        <h2 class="text-lg font-semibold">Add device</h2>
        <input v-model="addForm.name" class="input-field" placeholder="Name" required />
        <input v-model="addForm.description" class="input-field" placeholder="Description" />
        <template v-if="auth.can('add_device_ip') && subnets.length">
          <label class="flex items-center gap-2 text-sm">
            <input v-model="assignIpOnCreate" type="checkbox" @change="onAssignIpToggle" />
            Assign an IP address
          </label>
          <template v-if="assignIpOnCreate">
            <select v-model="addForm.site" class="input-field" @change="onAddSiteChange">
              <option v-for="site in sites" :key="site" :value="site">{{ site }}</option>
            </select>
            <select v-model="addForm.subnet_id" class="input-field" @change="onAddSubnetChange">
              <option v-for="s in subnetsForSite" :key="s.id" :value="s.id">{{ s.name }} ({{ s.cidr }})</option>
            </select>
            <select v-model="addForm.ip_id" class="input-field" required>
              <option v-for="ip in availableIps" :key="ip.id" :value="ip.id">{{ ip.ip }}</option>
            </select>
            <p v-if="addForm.subnet_id && !availableIps.length" class="text-xs text-slate-500">No available IPs in this subnet</p>
          </template>
        </template>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Create</button>
          <button type="button" class="btn-secondary" @click="showAdd = false">Cancel</button>
        </div>
      </form>
    </div>

    <div v-if="showBulk" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showBulk = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="bulkCreate">
        <h2 class="text-lg font-semibold">Bulk add devices</h2>
        <textarea v-model="bulkForm.names" class="input-field h-32" placeholder="One device name per line" required />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Create</button>
          <button type="button" class="btn-secondary" @click="showBulk = false">Cancel</button>
        </div>
      </form>
    </div>
  </div>
</template>
