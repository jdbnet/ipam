<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { api, type Rack } from "@/api";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const auth = useAuthStore();
const rack = ref<Rack | null>(null);
const showAddDevice = ref(false);
const showAddNonnet = ref(false);
const addForm = ref({ device_id: 0, position_u: 1, side: "front" });
const nonnetForm = ref({ nonnet_device_name: "", position_u: 1, side: "front" });
const err = ref("");

async function load() {
  rack.value = await api.rack(Number(route.params.id));
  const devs = rack.value?.site_devices || [];
  if (devs.length) addForm.value.device_id = devs[0].id;
}

onMounted(load);

const siteDevices = () => rack.value?.site_devices || [];

const slotsForSide = (r: Rack, rackSide: string) => {
  const h = r.height_u;
  const map: Record<number, typeof r.devices> = {};
  for (const d of r.devices || []) {
    if (d.side === rackSide) (map[d.position_u] ??= []).push(d);
  }
  return Array.from({ length: h }, (_, i) => ({ u: h - i, devices: map[h - i] || [] }));
};

async function addDevice() {
  err.value = "";
  try {
    await api.addRackDevice(Number(route.params.id), {
      device_id: addForm.value.device_id,
      position_u: addForm.value.position_u,
      side: addForm.value.side,
    });
    showAddDevice.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function addNonnet() {
  err.value = "";
  try {
    await api.addRackDevice(Number(route.params.id), {
      nonnet_device_name: nonnetForm.value.nonnet_device_name,
      position_u: nonnetForm.value.position_u,
      side: nonnetForm.value.side,
    });
    showAddNonnet.value = false;
    nonnetForm.value.nonnet_device_name = "";
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function removeDevice(rackDeviceId: number) {
  if (!confirm("Remove this device from the rack?")) return;
  await api.removeRackDevice(Number(route.params.id), rackDeviceId);
  await load();
}
</script>
<template>
  <div v-if="rack">
    <RouterLink to="/racks" class="text-sm text-accent hover:underline">← Racks</RouterLink>
    <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ rack.name }}</h1>
        <p class="text-slate-500">{{ rack.site }} · {{ rack.height_u }}U</p>
      </div>
      <a v-if="auth.can('export_rack_csv')" :href="`/api/v2/racks/${rack.id}/export`" class="btn-secondary text-sm">Export CSV</a>
    </div>
    <div class="mt-4 flex flex-wrap gap-2">
      <button v-if="auth.can('add_device_to_rack')" class="btn-secondary text-sm" @click="showAddDevice = true; err = ''">Add device</button>
      <button v-if="auth.can('add_nonnet_device_to_rack')" class="btn-secondary text-sm" @click="showAddNonnet = true; err = ''">Add non-networked</button>
    </div>

    <div class="mt-6 grid gap-6 lg:grid-cols-2">
      <div v-for="rackSide in ['front', 'back'] as const" :key="rackSide" class="card font-mono text-sm">
        <h2 class="mb-3 border-b border-slate-200 pb-2 text-base font-semibold capitalize dark:border-slate-700">{{ rackSide }}</h2>
        <div v-for="row in slotsForSide(rack, rackSide)" :key="row.u" class="flex border-b border-slate-200 py-2 dark:border-slate-700">
          <span class="w-10 shrink-0 text-slate-500">U{{ row.u }}</span>
          <span class="flex flex-1 flex-col gap-1">
            <span v-for="d in row.devices" :key="d.id" class="flex items-center gap-2">
              <RouterLink v-if="d.device_id" :to="`/devices/${d.device_id}`" class="text-accent hover:underline">{{ d.device_name }}</RouterLink>
              <span v-else>{{ d.nonnet_device_name }}</span>
              <button v-if="auth.can('remove_device_from_rack')" class="text-red-500 hover:underline" @click="removeDevice(d.id)">×</button>
            </span>
            <span v-if="!row.devices.length" class="text-slate-500">—</span>
          </span>
        </div>
      </div>
    </div>

    <div v-if="showAddDevice" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAddDevice = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="addDevice">
        <h2 class="text-lg font-semibold">Add device to rack</h2>
        <select v-model="addForm.device_id" class="input-field" required>
          <option v-for="d in siteDevices()" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <input v-model.number="addForm.position_u" type="number" :min="1" :max="rack.height_u" class="input-field" placeholder="U position" required />
        <select v-model="addForm.side" class="input-field">
          <option value="front">Front</option>
          <option value="back">Back</option>
        </select>
        <p class="text-xs text-slate-500">For multi-U devices, add each U separately.</p>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Add</button>
          <button type="button" class="btn-secondary" @click="showAddDevice = false">Cancel</button>
        </div>
      </form>
    </div>

    <div v-if="showAddNonnet" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAddNonnet = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="addNonnet">
        <h2 class="text-lg font-semibold">Add non-networked device</h2>
        <input v-model="nonnetForm.nonnet_device_name" class="input-field" placeholder="Device name" required />
        <input v-model.number="nonnetForm.position_u" type="number" :min="1" :max="rack.height_u" class="input-field" placeholder="U position" required />
        <select v-model="nonnetForm.side" class="input-field">
          <option value="front">Front</option>
          <option value="back">Back</option>
        </select>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Add</button>
          <button type="button" class="btn-secondary" @click="showAddNonnet = false">Cancel</button>
        </div>
      </form>
    </div>
  </div>
</template>
