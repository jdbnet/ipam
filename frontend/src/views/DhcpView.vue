<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { api } from "@/api";

const route = useRoute();
const pool = ref<{ start_ip?: string; end_ip?: string; excluded_ips?: string } | null>(null);
const form = ref({ start_ip: "", end_ip: "", excluded_ips: "" });
const msg = ref("");

onMounted(async () => {
  try {
    const d = await api.getDhcp(Number(route.params.id)) as { pools?: { start_ip: string; end_ip: string; excluded_ips?: string }[] };
    if (d.pools?.[0]) {
      pool.value = d.pools[0];
      form.value.start_ip = d.pools[0].start_ip;
      form.value.end_ip = d.pools[0].end_ip;
      form.value.excluded_ips = d.pools[0].excluded_ips || "";
    }
  } catch { /* no pool */ }
});

async function save() {
  await api.setDhcp(Number(route.params.id), {
    pools: [{ start_ip: form.value.start_ip, end_ip: form.value.end_ip, excluded_ips: form.value.excluded_ips.split(",").map((s) => s.trim()).filter(Boolean) }],
  });
  msg.value = "Saved";
}

async function remove() {
  await api.setDhcp(Number(route.params.id), { remove: true });
  pool.value = null;
  msg.value = "Removed";
}
</script>
<template>
  <div>
    <RouterLink :to="`/subnets/${route.params.id}`" class="text-sm text-accent hover:underline">← Subnet</RouterLink>
    <h1 class="mt-4 text-2xl font-bold">DHCP pool</h1>
    <form class="card mt-6 max-w-lg space-y-4" @submit.prevent="save">
      <input v-model="form.start_ip" class="input-field" placeholder="Start IP" required />
      <input v-model="form.end_ip" class="input-field" placeholder="End IP" required />
      <input v-model="form.excluded_ips" class="input-field" placeholder="Excluded IPs (comma-separated)" />
      <div class="flex gap-2">
        <button type="submit" class="btn-primary">Save</button>
        <button v-if="pool" type="button" class="btn-secondary" @click="remove">Remove pool</button>
      </div>
      <p v-if="msg" class="text-sm text-accent">{{ msg }}</p>
    </form>
  </div>
</template>
