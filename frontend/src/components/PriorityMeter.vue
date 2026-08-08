<script setup>
// PriorityMeter: a visual "fill" meter that reads left-to-right from LOW to
// HIGH priority. Left = grey/empty (lowest), right = red/hot (Critical).
// The STORED priority value follows the backend scale where 1 = Critical
// (highest) and 5 = Optional (lowest). So stored priority p (1..5) lights
// (6 - p) segments, and each segment stores 6 - itsLeftIndex.
const props = defineProps({
  modelValue: { type: Number, default: 3 },
  size: { type: String, default: 'sm' }, // 'xs' for task rows, 'sm' for toolbar
  light: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

// Rendered left -> right. Each entry's `set` is the stored priority value a
// click should write, and `color` is its lit appearance.
const SEGMENTS = [
  { set: 5, color: 'bg-zinc-400', bright: 'shadow-[0_0_6px_rgba(113,113,122,0.6)]', label: 'Optional' },
  { set: 4, color: 'bg-sky-400', bright: 'shadow-[0_0_6px_rgba(14,165,233,0.6)]', label: 'Low' },
  { set: 3, color: 'bg-yellow-400', bright: 'shadow-[0_0_6px_rgba(234,179,8,0.6)]', label: 'Medium' },
  { set: 2, color: 'bg-orange-400', bright: 'shadow-[0_0_6px_rgba(249,115,22,0.6)]', label: 'High' },
  { set: 1, color: 'bg-red-400', bright: 'shadow-[0_0_6px_rgba(239,68,68,0.7)]', label: 'Critical' },
]

// Number of lit segments for a given stored priority
function litCount(p) {
  return Math.max(0, Math.min(5, 6 - p))
}

const dimBar = props.light ? 'bg-zinc-200' : 'bg-zinc-700/60'
const sizeH = props.size === 'sm' ? 'h-3' : 'h-2.5'
const sizeW = props.size === 'sm' ? 'w-5' : 'w-4'

function activeLabel(p) {
  return (SEGMENTS.find(s => s.set === p) || SEGMENTS[4]).label
}
</script>

<template>
  <div
    class="flex items-end gap-[3px] shrink-0 group/meter"
    data-testid="priority-meter"
    :title="'Priority: ' + modelValue + ' (' + activeLabel(modelValue) + ')'"
  >
    <button
      v-for="(seg, i) in SEGMENTS"
      :key="seg.set"
      type="button"
      :data-priority="seg.set"
      @click="emit('update:modelValue', seg.set)"
      class="rounded-sm transition-all duration-150 cursor-pointer"
      :aria-label="seg.label"
      :class="[
        sizeW, sizeH,
        // Lit from the LEFT: segments left of/equal to the fill are colored.
        // The fill grows so the rightmost (hot/red) segment only lights at max.
        i < litCount(modelValue)
          ? `${seg.color} ${seg.bright} opacity-100`
          : `${dimBar} opacity-60 group-hover/meter:opacity-90`,
      ]"
    >
      <span class="sr-only">{{ seg.label }}</span>
    </button>
  </div>
</template>

