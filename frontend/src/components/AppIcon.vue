<script setup>
// Reusable Lucide-style icon set. Usage:
//   <AppIcon name="trash" class="w-4 h-4" />
// Icons inherit currentColor and accept any SVG sizing classes.
defineProps({
  name: { type: String, required: true },
})
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- Undo (↩) -->
    <template v-if="name === 'undo'">
      <path d="M3 7v6h6"/>
      <path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>
    </template>

    <!-- Repeat / recurring (⟳) -->
    <template v-else-if="name === 'repeat'">
      <path d="m17 2 4 4-4 4"/>
      <path d="M3 11v-1a4 4 0 0 1 4-4h14"/>
      <path d="m7 22-4-4 4-4"/>
      <path d="M21 13v1a4 4 0 0 1-4 4H3"/>
    </template>

    <!-- Chevron down (▾) -->
    <template v-else-if="name === 'chevron-down'">
      <path d="m6 9 6 6 6-6"/>
    </template>

    <!-- Chevron right (▸) -->
    <template v-else-if="name === 'chevron-right'">
      <path d="m9 18 6-6-6-6"/>
    </template>

    <!-- Trash (🗑) -->
    <template v-else-if="name === 'trash'">
      <path d="M3 6h18"/>
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
      <line x1="10" y1="11" x2="10" y2="17"/>
      <line x1="14" y1="11" x2="14" y2="17"/>
    </template>

    <!-- Sparkles (Organize) -->
    <template v-else-if="name === 'sparkles'">
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/>
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z"/>
    </template>

    <!-- Diamond logo mark (&#9670;) -->
    <template v-else-if="name === 'diamond'">
      <path d="M12 2 22 12 12 22 2 12Z"/>
    </template>

    <!-- Mic / recording dot (&#9679;) -->
    <template v-else-if="name === 'mic'">
      <rect x="9" y="2" width="6" height="11" rx="3"/>
      <path d="M5 10a7 7 0 0 1 14 0"/>
      <path d="M12 19v3M8 22h8"/>
    </template>

    <!-- Sun (light theme toggle) -->
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="4"/>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
    </template>

    <!-- Moon (dark theme toggle) -->
    <template v-else-if="name === 'moon'">
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
    </template>

    <!-- Alert triangle (offline) -->
    <template v-else-if="name === 'alert'">
      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </template>

    <!-- Minus (hide HUD) -->
    <template v-else-if="name === 'minus'">
      <path d="M5 12h14"/>
    </template>

    <!-- Spinner (loading) -->
    <template v-else-if="name === 'spinner'">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"/>
    </template>

    <!-- Play (start task) -->
    <template v-else-if="name === 'play'">
      <polygon points="6 3 20 12 6 21 6 3" fill="currentColor" stroke="none"/>
    </template>

    <!-- Pause (pause task) -->
    <template v-else-if="name === 'pause'">
      <rect x="6" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>
      <rect x="14" y="4" width="4" height="16" rx="1" fill="currentColor" stroke="none"/>
    </template>
  </svg>
</template>
