<template>
  <Teleport to="body">
    <div v-if="open" class="confirm-backdrop">
      <section class="confirm-dialog" role="dialog" aria-modal="true" :aria-labelledby="titleId">
        <header class="confirm-header">
          <RotomIcon class="confirm-icon" variant="pixel" />
          <h2 :id="titleId">{{ title }}</h2>
        </header>
        <p>{{ message }}</p>
        <footer class="confirm-actions">
          <button class="ghost-button" type="button" @click="emit('cancel')">Cancel</button>
          <button class="danger-button" type="button" @click="emit('confirm')">Delete</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import RotomIcon from "./RotomIcon.vue";

defineProps<{
  open: boolean;
  title: string;
  message: string;
}>();

const emit = defineEmits<{
  cancel: [];
  confirm: [];
}>();

const titleId = `confirm-title-${crypto.randomUUID()}`;
</script>
