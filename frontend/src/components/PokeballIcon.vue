<template>
  <span class="pokeball-icon" :class="{ tiny }">
    <img src="/assets/pokeball-pixel.jpg" alt="Poke Ball" draggable="false" />
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    tiny?: boolean;
  }>(),
  {
    tiny: false,
  },
);
</script>
