<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api, type Tag } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const tags = ref<Tag[]>([]);
const form = ref({ name: "", color: "#06b6d4", description: "" });
const editForm = ref({ id: 0, name: "", color: "#06b6d4", description: "" });
const showEdit = ref(false);
const loading = ref(true);
const err = ref("");

async function load() {
  loading.value = true;
  err.value = "";
  try {
    tags.value = await api.tags();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed to load tags";
    tags.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function create() {
  err.value = "";
  try {
    await api.createTag(form.value);
    form.value = { name: "", color: "#06b6d4", description: "" };
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function del(id: number) {
  if (!confirm("Delete tag?")) return;
  err.value = "";
  try {
    await api.deleteTag(id);
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

function openEdit(t: Tag) {
  editForm.value = { id: t.id, name: t.name, color: t.color || "#06b6d4", description: t.description || "" };
  showEdit.value = true;
  err.value = "";
}

async function saveEdit() {
  err.value = "";
  try {
    await api.updateTag(editForm.value.id, {
      name: editForm.value.name,
      color: editForm.value.color,
      description: editForm.value.description,
    });
    showEdit.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Tags</h1>
    <form v-if="auth.can('add_tag')" class="card mt-6 flex flex-wrap gap-3" @submit.prevent="create">
      <input v-model="form.name" class="input-field max-w-xs" placeholder="Name" required />
      <input v-model="form.color" type="color" class="h-10 w-14 rounded border-0" />
      <input v-model="form.description" class="input-field max-w-xs" placeholder="Description" />
      <button class="btn-primary">Add tag</button>
    </form>
    <p v-if="loading" class="mt-6 text-slate-500">Loading…</p>
    <p v-else-if="err && !tags.length" class="mt-6 text-red-500">{{ err }}</p>
    <p v-else-if="!tags.length" class="mt-6 text-slate-500">No tags yet.</p>
    <ul v-else class="mt-6 space-y-2">
      <li v-for="t in tags" :key="t.id" class="card flex items-center justify-between">
        <span><span class="inline-block h-3 w-3 rounded-full mr-2" :style="{ backgroundColor: t.color }" />{{ t.name }}</span>
        <div v-if="auth.can('edit_tag') || auth.can('delete_tag')" class="flex gap-2">
          <button v-if="auth.can('edit_tag')" class="text-sm text-accent hover:underline" @click="openEdit(t)">Edit</button>
          <button v-if="auth.can('delete_tag')" class="text-sm text-red-500" @click="del(t.id)">Delete</button>
        </div>
      </li>
    </ul>
    <p v-if="err && tags.length" class="mt-4 text-sm text-red-500">{{ err }}</p>

    <div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showEdit = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="saveEdit">
        <h2 class="text-lg font-semibold">Edit tag</h2>
        <input v-model="editForm.name" class="input-field" placeholder="Name" required />
        <input v-model="editForm.color" type="color" class="h-10 w-14 rounded border-0" />
        <input v-model="editForm.description" class="input-field" placeholder="Description" />
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Save</button>
          <button type="button" class="btn-secondary" @click="showEdit = false">Cancel</button>
        </div>
      </form>
    </div>
  </div>
</template>
