import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"), meta: { public: true } },
    { path: "/verify-2fa", name: "verify-2fa", component: () => import("@/views/Verify2faView.vue"), meta: { public: true } },
    { path: "/setup-2fa", name: "setup-2fa", component: () => import("@/views/Setup2faView.vue"), meta: { public: true } },
    {
      path: "/",
      component: () => import("@/components/AppLayout.vue"),
      children: [
        { path: "", name: "dashboard", component: () => import("@/views/DashboardView.vue") },
        { path: "devices", name: "devices", component: () => import("@/views/DevicesView.vue") },
        { path: "devices/:id", name: "device", component: () => import("@/views/DeviceDetailView.vue") },
        { path: "subnets/:id", name: "subnet", component: () => import("@/views/SubnetDetailView.vue") },
        { path: "subnets/:id/dhcp", redirect: (to) => `/subnets/${to.params.id}` },
        { path: "racks", name: "racks", component: () => import("@/views/RacksView.vue") },
        { path: "racks/:id", name: "rack", component: () => import("@/views/RackDetailView.vue") },
        { path: "search", redirect: "/" },
        { path: "tags", name: "tags", component: () => import("@/views/TagsView.vue") },
        { path: "device-types", redirect: "/devices" },
        { path: "custom-fields", name: "custom-fields", component: () => import("@/views/CustomFieldsView.vue") },
        { path: "bulk", redirect: "/devices" },
        { path: "audit", name: "audit", component: () => import("@/views/AuditView.vue") },
        { path: "subnets/manage", name: "subnet-management", component: () => import("@/views/SubnetsView.vue") },
        { path: "admin", redirect: "/subnets/manage" },
        { path: "users", name: "users", component: () => import("@/views/UsersView.vue") },
        { path: "account", name: "account", component: () => import("@/views/AccountView.vue") },
      ],
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (!auth.loaded) await auth.fetchMe().catch(() => {});
  if (to.meta.public) return true;
  if (!auth.loggedIn) return { name: "login", query: { redirect: to.fullPath } };
  return true;
});

export { router };
export default router;
