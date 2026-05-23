<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { api, type Subnet } from "@/api";
import { useAuthStore } from "@/stores/auth";
import IpHistoryModal from "@/components/IpHistoryModal.vue";
import DhcpModal from "@/components/DhcpModal.vue";
import CustomFieldValues from "@/components/CustomFieldValues.vue";

const route = useRoute();
const auth = useAuthStore();
const subnet = ref<Subnet | null>(null);
const historyIp = ref<string | null>(null);
const showDhcp = ref(false);
const loading = ref(true);
const error = ref("");
const notesErr = ref("");

async function loadSubnet() {
  loading.value = true;
  error.value = "";
  try {
    subnet.value = await api.subnet(Number(route.params.id));
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Failed to load subnet";
    subnet.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(loadSubnet);

async function saveNotes(ipId: number, notes: string) {
  notesErr.value = "";
  try {
    await api.patchIpNotes(ipId, notes);
  } catch (e) {
    notesErr.value = e instanceof Error ? e.message : "Failed to save notes";
  }
}

function onCustomFieldsSaved(values: Record<string, unknown>) {
  if (subnet.value) subnet.value.custom_fields = values;
}

function isDhcpRow(hostname?: string) {
  return hostname === "DHCP";
}
</script>
<template>
  <div>
    <RouterLink to="/subnets" class="text-sm text-accent hover:underline">← Subnets</RouterLink>
    <p v-if="loading" class="mt-8 text-slate-500">Loading…</p>
    <p v-else-if="error" class="mt-8 text-red-500">{{ error }}</p>
    <template v-else-if="subnet">
      <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-bold">{{ subnet.name }}</h1>
          <div class="mt-1 flex flex-wrap items-center gap-2 font-mono text-slate-500">
            <span>{{ subnet.cidr }} · {{ subnet.site || "Unassigned" }}</span>
            <span
              v-if="subnet.vlan_id"
              class="rounded-full bg-surface-overlay px-2 py-0.5 text-xs font-semibold font-sans text-slate-600 dark:text-slate-300"
            >VLAN {{ subnet.vlan_id }}</span>
          </div>
          <p v-if="subnet.vlan_description" class="mt-1 text-sm text-slate-500">{{ subnet.vlan_description }}</p>
          <p v-if="subnet.vlan_notes" class="text-sm text-slate-400">{{ subnet.vlan_notes }}</p>
        </div>
        <div class="flex gap-2">
          <button
            v-if="auth.can('view_dhcp') || auth.can('configure_dhcp')"
            type="button"
            class="btn-secondary text-sm"
            @click="showDhcp = true"
          >
            DHCP
          </button>
          <a v-if="auth.can('export_subnet_csv')" :href="`/api/v2/subnets/${subnet.id}/export`" class="btn-secondary text-sm">Export CSV</a>
        </div>
      </div>

      <CustomFieldValues
        v-if="auth.can('view_custom_fields')"
        class="mt-6"
        entity-type="subnet"
        :entity-id="subnet.id"
        :values="subnet.custom_fields"
        :can-edit="auth.can('edit_subnet')"
        @saved="onCustomFieldsSaved"
      />

      <div class="card mt-6 overflow-x-auto">
        <p v-if="notesErr" class="mb-2 text-sm text-red-500">{{ notesErr }}</p>
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
            <tr
              v-for="ip in subnet.ip_addresses"
              :key="ip.id"
              class="border-b border-slate-100 dark:border-slate-800"
              :class="isDhcpRow(ip.hostname) ? 'bg-amber-50/80 italic dark:bg-amber-950/20' : ''"
            >
              <td class="p-2 font-mono">{{ ip.ip }}</td>
              <td class="p-2" :class="isDhcpRow(ip.hostname) ? 'text-amber-700 dark:text-amber-400' : ''">
                <RouterLink v-if="ip.device_id" :to="`/devices/${ip.device_id}`" class="text-accent hover:underline not-italic">{{ ip.device_name || ip.hostname }}</RouterLink>
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
            <tr v-if="!subnet.ip_addresses?.length">
              <td colspan="4" class="p-4 text-center text-slate-500">No IP addresses in this subnet.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <IpHistoryModal :ip="historyIp" @close="historyIp = null" />
      <DhcpModal :open="showDhcp" :subnet-id="subnet.id" @close="showDhcp = false" @saved="loadSubnet" />
    </template>
  </div>
</template>
