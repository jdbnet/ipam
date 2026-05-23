<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api, type AuditEntry } from "@/api";
import { formatLocalTime } from "@/utils/datetime";

const logs = ref<AuditEntry[]>([]);

onMounted(async () => { logs.value = await api.audit(200); });
</script>
<template>
  <div>
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">Audit log</h1>
      <a href="/api/v2/audit/export" class="btn-secondary text-sm">Export CSV</a>
    </div>
    <div class="card mt-6 overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead><tr class="border-b dark:border-slate-700"><th class="p-2">Time</th><th class="p-2">User</th><th class="p-2">Action</th><th class="p-2">Details</th></tr></thead>
        <tbody>
          <tr v-for="l in logs" :key="l.id" class="border-b dark:border-slate-800">
            <td class="p-2 whitespace-nowrap text-xs text-slate-500">{{ formatLocalTime(l.timestamp) }}</td>
            <td class="p-2">{{ l.user_name }}</td>
            <td class="p-2 font-mono text-xs">{{ l.action }}</td>
            <td class="p-2 max-w-md truncate">{{ l.details }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
