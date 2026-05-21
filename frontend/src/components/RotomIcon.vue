<template>
  <span class="rotom-image-frame" :class="`is-${variant}`">
    <img :src="src" :alt="alt" draggable="false" />
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?: "pixel" | "official" | "small";
    alt?: string;
  }>(),
  {
    variant: "pixel",
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
  return "/assets/rotom-pixel-transparent.png";
});
</script>
