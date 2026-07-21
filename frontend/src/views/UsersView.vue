<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { api, type UserRow, type RoleRow } from "@/api";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const tab = ref<"users" | "roles">("users");
const users = ref<UserRow[]>([]);
const roles = ref<RoleRow[]>([]);
const permissions = ref<{ id: number; name: string; category?: string }[]>([]);
const err = ref("");

const showUserForm = ref(false);
const editUserId = ref<number | null>(null);
const userForm = ref({ name: "", email: "", password: "", role_id: 0 });

const showRoleForm = ref(false);
const editRoleId = ref<number | null>(null);
const roleForm = ref({ name: "", description: "", require_2fa: false, permission_ids: [] as number[] });

const showApiKey = ref("");
const permByCategory = computed(() => {
  const m: Record<string, typeof permissions.value> = {};
  for (const p of permissions.value) {
    const cat = p.category || "Other";
    (m[cat] ??= []).push(p);
  }
  return m;
});

async function load() {
  [users.value, roles.value] = await Promise.all([api.users(), api.roles()]);
  if (auth.can("manage_roles")) {
    permissions.value = await api.permissions().catch(() => []);
  }
}

onMounted(load);

function openAddUser() {
  editUserId.value = null;
  userForm.value = { name: "", email: "", password: "", role_id: roles.value[0]?.id ?? 0 };
  showUserForm.value = true;
  err.value = "";
}

function openEditUser(u: UserRow) {
  editUserId.value = u.id;
  userForm.value = { name: u.name, email: u.email, password: "", role_id: u.role_id ?? 0 };
  showUserForm.value = true;
  err.value = "";
}

async function saveUser() {
  err.value = "";
  try {
    if (editUserId.value) {
      const body: Record<string, unknown> = { name: userForm.value.name, email: userForm.value.email, role_id: userForm.value.role_id };
      if (userForm.value.password) body.password = userForm.value.password;
      await api.updateUser(editUserId.value, body);
    } else {
      await api.createUser(userForm.value);
    }
    showUserForm.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function delUser(id: number) {
  if (!confirm("Delete this user?")) return;
  await api.deleteUser(id);
  await load();
}

async function regenKey(id: number) {
  if (!confirm("Regenerate API key? The old key will stop working.")) return;
  const r = await api.regenerateApiKey(id);
  showApiKey.value = r.api_key;
}

function openAddRole() {
  editRoleId.value = null;
  roleForm.value = { name: "", description: "", require_2fa: false, permission_ids: [] };
  showRoleForm.value = true;
  err.value = "";
}

function openEditRole(r: RoleRow) {
  editRoleId.value = r.id;
  roleForm.value = {
    name: r.name,
    description: r.description || "",
    require_2fa: !!r.require_2fa,
    permission_ids: r.permissions?.map((p) => p.id) ?? [],
  };
  showRoleForm.value = true;
  err.value = "";
}

function togglePerm(id: number) {
  const idx = roleForm.value.permission_ids.indexOf(id);
  if (idx >= 0) roleForm.value.permission_ids.splice(idx, 1);
  else roleForm.value.permission_ids.push(id);
}

async function saveRole() {
  err.value = "";
  try {
    if (editRoleId.value) {
      await api.updateRole(editRoleId.value, roleForm.value);
    } else {
      await api.createRole(roleForm.value);
    }
    showRoleForm.value = false;
    await load();
  } catch (e) {
    err.value = e instanceof Error ? e.message : "Failed";
  }
}

async function delRole(id: number) {
  if (!confirm("Delete this role?")) return;
  await api.deleteRole(id);
  await load();
}
</script>
<template>
  <div>
    <h1 class="text-2xl font-bold">Users & roles</h1>
    <div class="mt-4 flex gap-2">
      <button class="rounded-lg px-3 py-1 text-sm" :class="tab === 'users' ? 'bg-accent text-slate-950' : 'bg-surface-overlay'" @click="tab = 'users'">Users</button>
      <button class="rounded-lg px-3 py-1 text-sm" :class="tab === 'roles' ? 'bg-accent text-slate-950' : 'bg-surface-overlay'" @click="tab = 'roles'">Roles</button>
    </div>

    <section v-if="tab === 'users'" class="mt-8">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 class="font-semibold text-accent">Users</h2>
        <div class="flex flex-wrap gap-2">
          <a href="/api/docs" target="_blank" rel="noopener noreferrer" class="btn-secondary text-sm">API documentation</a>
          <button v-if="auth.can('manage_users')" class="btn-primary text-sm" @click="openAddUser">Add user</button>
        </div>
      </div>
      <ul class="space-y-2">
        <li
          class="hidden px-4 text-xs font-medium text-slate-500 sm:grid sm:grid-cols-[minmax(0,1fr)_8rem_13rem] sm:items-center sm:gap-4"
        >
          <span>User</span>
          <span>Role</span>
          <span v-if="auth.can('manage_users')" class="text-right">Actions</span>
        </li>
        <li
          v-for="u in users"
          :key="u.id"
          class="card grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_13rem] sm:items-center sm:gap-4"
        >
          <span class="min-w-0">{{ u.name }} <span class="text-slate-500">&lt;{{ u.email }}&gt;</span></span>
          <span class="text-sm text-slate-500">{{ u.role_name }}</span>
          <div v-if="auth.can('manage_users')" class="flex gap-2 sm:justify-end">
            <button class="text-sm text-accent hover:underline" @click="openEditUser(u)">Edit</button>
            <button class="text-sm text-accent hover:underline" @click="regenKey(u.id)">API key</button>
            <button class="text-sm text-red-500 hover:underline" @click="delUser(u.id)">Delete</button>
          </div>
        </li>
      </ul>
    </section>

    <section v-if="tab === 'roles'" class="mt-8">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="font-semibold text-accent">Roles</h2>
        <button v-if="auth.can('manage_roles')" class="btn-primary text-sm" @click="openAddRole">Add role</button>
      </div>
      <ul class="space-y-2">
        <li v-for="r in roles" :key="r.id" class="card">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div class="font-medium">{{ r.name }} <span v-if="r.require_2fa" class="text-xs text-slate-500">(2FA required)</span></div>
              <div class="text-sm text-slate-500">{{ r.description }}</div>
            </div>
            <div v-if="auth.can('manage_roles')" class="flex gap-2">
              <button class="text-sm text-accent hover:underline" @click="openEditRole(r)">Edit</button>
              <button class="text-sm text-red-500 hover:underline" @click="delRole(r.id)">Delete</button>
            </div>
          </div>
        </li>
      </ul>
    </section>

    <div v-if="showUserForm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showUserForm = false">
      <form class="card w-full max-w-md space-y-3" @submit.prevent="saveUser">
        <h2 class="text-lg font-semibold">{{ editUserId ? "Edit user" : "Add user" }}</h2>
        <input v-model="userForm.name" class="input-field" placeholder="Name" required />
        <input v-model="userForm.email" type="email" class="input-field" placeholder="Email" required />
        <input v-model="userForm.password" type="password" class="input-field" :placeholder="editUserId ? 'New password (optional)' : 'Password'" :required="!editUserId" />
        <select v-model="userForm.role_id" class="input-field">
          <option v-for="r in roles" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Save</button>
          <button type="button" class="btn-secondary" @click="showUserForm = false">Cancel</button>
        </div>
      </form>
    </div>

    <div v-if="showRoleForm" class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-[10vh]" @click.self="showRoleForm = false">
      <form class="card w-full max-w-lg space-y-3" @submit.prevent="saveRole">
        <h2 class="text-lg font-semibold">{{ editRoleId ? "Edit role" : "Add role" }}</h2>
        <input v-model="roleForm.name" class="input-field" placeholder="Name" required />
        <input v-model="roleForm.description" class="input-field" placeholder="Description" />
        <label class="flex items-center gap-2 text-sm">
          <input v-model="roleForm.require_2fa" type="checkbox" />
          Require 2FA
        </label>
        <div v-if="permissions.length" class="max-h-48 overflow-y-auto rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <div v-for="(perms, cat) in permByCategory" :key="cat" class="mb-3">
            <div class="text-xs font-semibold uppercase text-slate-500">{{ cat }}</div>
            <label v-for="p in perms" :key="p.id" class="mt-1 flex items-center gap-2 text-sm">
              <input type="checkbox" :checked="roleForm.permission_ids.includes(p.id)" @change="togglePerm(p.id)" />
              {{ p.name }}
            </label>
          </div>
        </div>
        <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
        <div class="flex gap-2">
          <button type="submit" class="btn-primary">Save</button>
          <button type="button" class="btn-secondary" @click="showRoleForm = false">Cancel</button>
        </div>
      </form>
    </div>

    <div v-if="showApiKey" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="showApiKey = ''">
      <div class="card w-full max-w-md space-y-3">
        <h2 class="text-lg font-semibold">New API key</h2>
        <p class="text-sm text-slate-500">Copy this key now - it won't be shown again.</p>
        <code class="block break-all rounded-lg bg-surface-overlay p-3 text-sm">{{ showApiKey }}</code>
        <button class="btn-primary" @click="showApiKey = ''">Done</button>
      </div>
    </div>
  </div>
</template>
