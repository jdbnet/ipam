<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { api, type Subnet } from "@/api";
import { useAuthStore } from "@/stores/auth";
import IpHistoryModal from "@/components/IpHistoryModal.vue";

const route = useRoute();
const auth = useAuthStore();
const subnet = ref<Subnet | null>(null);
const historyIp = ref<string | null>(null);

onMounted(async () => {
  subnet.value = await api.subnet(Number(route.params.id));
});

async function saveNotes(ipId: number, notes: string) {
  await api.patchIpNotes(ipId, notes);
}
</script>
<template>
  <div v-if="subnet">
    <RouterLink to="/" class="text-sm text-accent hover:underline">← Home</RouterLink>
    <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold">{{ subnet.name }}</h1>
        <p class="font-mono text-slate-500">{{ subnet.cidr }} · {{ subnet.site || "Unassigned" }}</p>
      </div>
      <div class="flex gap-2">
        <RouterLink :to="`/subnets/${subnet.id}/dhcp`" class="btn-secondary text-sm">DHCP</RouterLink>
        <a v-if="auth.can('export_subnet_csv')" :href="`/api/v2/subnets/${subnet.id}/export`" class="btn-secondary text-sm">Export CSV</a>
      </div>
    </div>
    <div class="card mt-6 overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="border-b border-slate-200 dark:border-slate-700">
            <th class="p-2 font-medium">IP</th>
            <th class="p-2 font-medium">Hostname</th>
            <th class="p-2 font-medium">Notes</th>
            <th class="p-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="ip in subnet.ip_addresses" :key="ip.id" class="border-b border-slate-100 dark:border-slate-800">
            <td class="p-2 font-mono">{{ ip.ip }}</td>
            <td class="p-2">
              <RouterLink v-if="ip.device_id" :to="`/devices/${ip.device_id}`" class="text-accent hover:underline">{{ ip.device_name || ip.hostname }}</RouterLink>
              <span v-else>{{ ip.hostname || "—" }}</span>
            </td>
            <td class="p-2">
              <input
                v-if="auth.can('edit_subnet')"
                :value="ip.notes || ''"
                class="input-field py-1 text-xs"
                @change="saveNotes(ip.id, ($event.target as HTMLInputElement).value)"
              />
              <span v-else>{{ ip.notes || "—" }}</span>
            </td>
            <td class="p-2">
              <button type="button" class="text-xs text-accent hover:underline" @click="historyIp = ip.ip">History</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <IpHistoryModal :ip="historyIp" @close="historyIp = null" />
  </div>
</template>
