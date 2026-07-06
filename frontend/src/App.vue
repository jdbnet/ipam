<script setup lang="ts">
import { watch, onMounted } from "vue";
import { RouterView } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();

function hexToRgb(hex: string) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex.trim());
  return result ? `${parseInt(result[1], 16)} ${parseInt(result[2], 16)} ${parseInt(result[3], 16)}` : null;
}

function applyAccentColor() {
  const color = auth.org?.accent_color;
  if (color) {
    const rgb = color.startsWith('#') ? hexToRgb(color) : color;
    if (rgb) {
      document.documentElement.style.setProperty("--accent", rgb);
      document.documentElement.style.setProperty("--accent-muted", rgb);
    }
  }
}

onMounted(() => {
  applyAccentColor();
});

watch(() => auth.org?.accent_color, applyAccentColor);

</script>
<template>
  <RouterView />
</template>
