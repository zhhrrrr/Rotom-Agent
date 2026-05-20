<template>
  <span class="rotom-image-frame" :class="[`is-${variant}`, { 'is-badge': badge }]">
    <img :src="src" :alt="alt" draggable="false" />
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?: "pixel" | "official" | "small";
    badge?: boolean;
    alt?: string;
  }>(),
  {
    variant: "pixel",
    badge: false,
    alt: "Rotom",
  },
);

const src = computed(() => {
  if (props.variant === "official") {
    return "/assets/rotom-official.png";
  }
  if (props.variant === "small") {
    return "/assets/rotom-small.png";
  }
  return "/assets/rotom-pixel.jpg";
});
</script>
