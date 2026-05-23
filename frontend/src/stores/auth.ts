import { defineStore } from "pinia";
import { api, type MeResponse } from "@/api";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    loaded: false,
    loggedIn: false,
    user: null as MeResponse["user"] | null,
    permissions: [] as string[],
    org: { name: "IPAM", logo: "" },
    version: "unknown",
  }),
  getters: {
    can: (state) => (perm: string) => state.permissions.includes(perm),
  },
  actions: {
    async fetchMe() {
      const data = await api.me();
      this.loaded = true;
      this.loggedIn = data.logged_in;
      this.user = data.user ?? null;
      this.permissions = data.permissions ?? [];
      this.org = data.org ?? this.org;
      this.version = data.app_version ?? "unknown";
    },
    async login(email: string, password: string) {
      return api.login(email, password);
    },
    async logout() {
      await api.logout();
      this.loggedIn = false;
      this.user = null;
      this.permissions = [];
    },
  },
});
