import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { setUnauthorizedHandler } from "./api";
import { useAuthStore } from "./stores/auth";
import "./style.css";

const pinia = createPinia();
const app = createApp(App);
app.use(pinia).use(router);

setUnauthorizedHandler(() => {
  const auth = useAuthStore();
  const current = router.currentRoute.value;
  if (current.meta.public) return;
  auth.logout();
  router.push({ name: "login", query: { redirect: current.fullPath } });
});

app.mount("#app");
