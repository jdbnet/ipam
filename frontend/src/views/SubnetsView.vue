<script setup lang="ts">
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { api, type Subnet } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const subnets = ref<Subnet[]>([]);
const form = ref({ name: "", cidr: "", site: "", vlan_id: "" as string | number, vlan_description: "", vlan_notes: "" });
const editForm = ref({ id: 0, name: "", cidr: "", site: "", vlan_id: "" as string | number, vlan_description: "", vlan_notes: "" });
const showEdit = ref(false);
const err = ref("");

onMounted(async () => { subnets.value = await api.subnets(); });

async function reload() {
  subnets.value = await api.subnets();
}

async function add() {
  err.value = "";
  try {
    const body: Partial<Subnet> = {
      name: form.value.name,
      cidr: form.value.cidr,
      site: form.value.site,
      vlan_description: form.value.vlan_description || undefined,
      vlan_notes: form.value.vlan_notes || undefined,
    };
    if (form.value.vlan_id) body.vlan_id = Number(form.value.vlan_id);
    await api.createSubnet(body);
    form.value = { name: "", cidr: "", site: "", vlan_id: "", vlan_description: "", vlan_notes: "" };
    await reload();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

function openEdit(s: Subnet) {
  editForm.value = {
    id: s.id,
    name: s.name,
    cidr: s.cidr,
    site: s.site || "",
    vlan_id: s.vlan_id ?? "",
    vlan_description: s.vlan_description || "",
    vlan_notes: s.vlan_notes || "",
  };
  showEdit.value = true;
  err.value = "";
}

async function saveEdit() {
  err.value = "";
  try {
    const body: Partial<Subnet> = {
      name: editForm.value.name,
      cidr: editForm.value.cidr,
      site: editForm.value.site,
      vlan_description: editForm.value.vlan_description || null,
      vlan_notes: editForm.value.vlan_notes || null,
      vlan_id: editForm.value.vlan_id ? Number(editForm.value.vlan_id) : null,
    };
    await api.updateSubnet(editForm.value.id, body);
    showEdit.value = false;
    await reload();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function del(id: number) {
  if (!confirm("Delete subnet and all IPs?")) return;
  await api.deleteSubnet(id);
  await reload();
}
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Subnet management</h1>
    <form v-if="auth.can('add_subnet')" class="card mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" @submit.prevent="add">
      <input v-model="form.name" class="input-field" placeholder="Name" required />
      <input v-model="form.cidr" class="input-field font-mono" placeholder="192.168.1.0/24" required />
      <input v-model="form.site" class="input-field" placeholder="Site" />
      <input v-model="form.vlan_id" type="number" class="input-field" placeholder="VLAN ID" min="1" max="4094" />
      <input v-model="form.vlan_description" class="input-field" placeholder="VLAN description" />
      <input v-model="form.vlan_notes" class="input-field" placeholder="VLAN notes" />
      <button class="btn-primary sm:col-span-2 lg:col-span-3 sm:max-w-xs">Add subnet</button>
      <p v-if="err" class="text-sm text-red-500 sm:col-span-3">{{ err }}</p>
    </form>
    <ul class="mt-8 space-y-2">
      <li v-for="s in subnets" :key="s.id" class="card flex flex-wrap items-center justify-between gap-2">
        <RouterLink :to="`/subnets/${s.id}`" class="font-medium text-accent hover:underline">{{ s.name }}</RouterLink>
        <span class="font-mono text-sm text-slate-500">{{ s.cidr }}</span>
        <span v-if="s.vlan_id" class="rounded-full bg-surface-overlay px-2 py-0.5 text-xs">VLAN {{ s.vlan_id }}</span>
        <div class="flex gap-2">
          <button v-if="auth.can('edit_subnet')" class="text-sm text-accent hover:underline" @click="openEdit(s)">Edit</button>
          <button v-if="auth.can('delete_subnet')" class="text-sm text-red-500" @click="del(s.id)">Delete</button>
        </div>
      </li>
    </ul>

    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showEdit = false">
      <form class="card w-full max-w-lg space-y-3" @submit.prevent="saveEdit">
        <h2 class="text-lg font-semibold">Edit subnet</h2>
        <input v-model="editForm.name" class="input-field" placeholder="Name" required />
        <input v-model="editForm.cidr" class="input-field font-mono" placeholder="CIDR" required />
        <input v-model="editForm.site" class="input-field" placeholder="Site" />
        <input v-model="editForm.vlan_id" type="number" class="input-field" placeholder="VLAN ID" min="1" max="4094" />
        <input v-model="editForm.vlan_description" class="input-field" placeholder="VLAN description" />
        <input v-model="editForm.vlan_notes" class="input-field" placeholder="VLAN notes" />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Save</button>
          <button type="button" class="btn-secondary" @click="showEdit = false">Cancel</button>
        </div>
      </form>
    </div>
  </div>
</template>
