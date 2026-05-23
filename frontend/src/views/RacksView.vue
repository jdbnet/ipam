<script setup lang="ts">
import { ref, onMounted } from "vue";
import { RouterLink } from "vue-router";
import { api, type Rack } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const racks = ref<Rack[]>([]);
const showAdd = ref(false);
const showEdit = ref(false);
const form = ref({ name: "", site: "", height_u: 42 });
const editId = ref(0);
const loading = ref(true);
const err = ref("");

async function load() {
  loading.value = true;
  err.value = "";
  try {
    racks.value = await api.racks();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to load racks";
    racks.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function create() {
  err.value = "";
  try {
    await api.createRack({ ...form.value, height_u: Number(form.value.height_u) });
    showAdd.value = false;
    form.value = { name: "", site: "", height_u: 42 };
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

function openEdit(r: Rack) {
  editId.value = r.id;
  form.value = { name: r.name, site: r.site, height_u: r.height_u };
  showEdit.value = true;
  err.value = "";
}

async function saveEdit() {
  err.value = "";
  try {
    await api.updateRack(editId.value, { ...form.value, height_u: Number(form.value.height_u) });
    showEdit.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function del(id: number) {
  if (!confirm("Delete this rack?")) return;
  await api.deleteRack(id);
  await load();
}
</script>
<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-2xl font-bold">Racks</h1>
      <button v-if="auth.can('add_rack')" class="btn-primary text-sm" @click="showAdd = true; err = ''">Add rack</button>
    </div>
    <p v-if="loading" class="mt-6 text-slate-500">Loading…</p>
    <p v-else-if="err && !racks.length" class="mt-6 text-red-500">{{ err }}</p>
    <p v-else-if="!racks.length" class="mt-6 text-slate-500">No racks yet.</p>
    <div v-else class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="r in racks" :key="r.id" class="card">
        <RouterLink :to="`/racks/${r.id}`" class="block transition hover:text-accent">
          <div class="font-medium">{{ r.name }}</div>
          <div class="text-sm text-slate-500">{{ r.site }} · {{ r.height_u }}U · {{ r.percent_full ?? 0 }}% full</div>
        </RouterLink>
        <div v-if="auth.can('add_rack') || auth.can('delete_rack')" class="mt-3 flex gap-2">
          <button v-if="auth.can('add_rack')" class="text-sm text-accent hover:underline" @click="openEdit(r)">Edit</button>
          <button v-if="auth.can('delete_rack')" class="text-sm text-red-500 hover:underline" @click="del(r.id)">Delete</button>
        </div>
      </div>
    </div>

    <div v-if="showAdd || showEdit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showAdd = false; showEdit = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="showEdit ? saveEdit() : create()">
        <h2 class="text-lg font-semibold">{{ showEdit ? "Edit rack" : "Add rack" }}</h2>
        <input v-model="form.name" class="input-field" placeholder="Name" required />
        <input v-model="form.site" class="input-field" placeholder="Site" required />
        <input v-model.number="form.height_u" type="number" min="1" class="input-field" placeholder="Height (U)" required />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">{{ showEdit ? "Save" : "Create" }}</button>
          <button type="button" class="btn-secondary" @click="showAdd = false; showEdit = false">Cancel</button>
        </div>
      </form>
    </div>
  </div>
</template>
