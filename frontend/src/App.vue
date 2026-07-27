<script setup>
import { ref } from 'vue'

const brainDump = ref('')
const tasks = ref([])

function handleDump() {
  if (!brainDump.value.trim()) return
  tasks.value.push({
    id: Date.now(),
    text: brainDump.value,
    done: false,
  })
  brainDump.value = ''
}
</script>

<template>
  <div class="h-screen w-screen bg-black/80 text-green-400 font-mono p-4 flex flex-col overflow-hidden">
    <header class="flex-none border-b border-green-400/30 pb-2 mb-4">
      <h1 class="text-lg font-bold tracking-widest">DISPATCH // AI</h1>
      <p class="text-xs text-green-400/60">~ hud active ~</p>
    </header>
    <div class="flex-none mb-4">
      <textarea
        v-model="brainDump"
        @keydown.ctrl.enter="handleDump"
        placeholder="> brain dump here... (Ctrl+Enter to submit)"
        class="w-full bg-black/40 border border-green-400/30 rounded p-2 text-sm text-green-300 placeholder-green-400/40 resize-none focus:outline-none focus:border-green-400/60"
        rows="3"
      />
      <button
        @click="handleDump"
        class="mt-1 text-xs border border-green-400/40 px-3 py-1 rounded hover:bg-green-400/10 active:bg-green-400/20 transition-colors"
      >[process]</button>
    </div>
    <div class="flex-1 overflow-y-auto space-y-1">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="flex items-center gap-2 text-sm border-l-2 border-green-400/40 pl-2 py-1 hover:bg-green-400/5"
      >
        <input type="checkbox" v-model="task.done" class="accent-green-400" />
        <span :class="{ 'line-through text-green-400/40': task.done }">{{ task.text }}</span>
      </div>
      <p v-if="tasks.length === 0" class="text-green-400/30 text-xs italic">no tasks yet. type something above.</p>
    </div>
    <footer class="flex-none border-t border-green-400/30 pt-2 mt-4 text-xs text-green-400/50 flex justify-between">
      <span>tasks: {{ tasks.length }}</span>
      <span>ctrl+space to focus</span>
    </footer>
  </div>
</template>
