<script setup>
import { ref, computed } from 'vue'

const theme = ref('dark')
const brainDump = ref('')
const tasks = ref([])
const isListening = ref(false)

const isDark = computed(() => theme.value === 'dark')

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}

function handleDump() {
  if (!brainDump.value.trim()) return
  tasks.value.push({
    id: Date.now(),
    text: brainDump.value,
    done: false,
  })
  brainDump.value = ''
}

function clearDone() {
  tasks.value = tasks.value.filter(t => !t.done)
}

function toggleMic() {
  isListening.value = !isListening.value
  // TODO: connect to speech-to-text
}
</script>

<template>
  <!-- Dark theme -->
  <div
    v-if="isDark"
    class="h-screen w-screen bg-zinc-900/95 text-zinc-100 p-5 flex flex-col overflow-hidden select-none"
  >
    <header class="flex-none flex items-center justify-between pb-3 mb-3 border-b border-zinc-700/50">
      <div>
        <h1 class="text-base font-semibold tracking-wider text-zinc-100">
          <span class="text-sky-400">◆</span> DISPATCH
        </h1>
        <p class="text-[11px] text-zinc-500">ai-powered task hud</p>
      </div>
      <button
        @click="toggleTheme"
        class="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-800 flex items-center gap-1.5"
        title="Switch to light theme"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="4"/>
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
        </svg>
      </button>
    </header>

    <div class="flex-none mb-4">
      <textarea
        v-model="brainDump"
        @keydown.ctrl.enter="handleDump"
        placeholder="Brain dump here... (Ctrl+Enter to submit)"
        class="w-full bg-zinc-800/80 border border-zinc-700/60 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-500 resize-none focus:outline-none focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/20 transition-all"
        rows="3"
      />
      <div class="flex gap-2 mt-2">
        <button
          @click="toggleMic"
          class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all"
          :class="isListening
            ? 'bg-red-500/20 text-red-400 border border-red-500/40 animate-pulse'
            : 'bg-zinc-800 text-zinc-400 border border-zinc-700/50 hover:text-zinc-200 hover:border-zinc-600'"
          :title="isListening ? 'Stop recording' : 'Start voice input'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="2" width="6" height="11" rx="3"/>
            <path d="M5 10a7 7 0 0114 0"/>
            <path d="M12 19v3M8 22h8"/>
          </svg>
          {{ isListening ? 'Listening...' : 'Voice' }}
        </button>
        <button
          @click="handleDump"
          class="text-xs bg-sky-500/10 text-sky-400 border border-sky-500/30 px-3 py-1.5 rounded-md hover:bg-sky-500/20 active:bg-sky-500/30 transition-all"
        >
          + Add Task
        </button>
        <button
          v-if="tasks.some(t => t.done)"
          @click="clearDone"
          class="text-xs text-zinc-500 border border-zinc-700/50 px-3 py-1.5 rounded-md hover:text-zinc-300 hover:border-zinc-600 transition-all"
        >
          Clear done
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto space-y-0.5">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="flex items-center gap-3 px-3 py-2 rounded-md transition-all cursor-default"
        :class="task.done ? 'bg-zinc-800/30' : 'hover:bg-zinc-800/50'"
      >
        <input
          type="checkbox"
          v-model="task.done"
          class="appearance-none w-4 h-4 rounded border-2 border-zinc-600 checked:border-sky-500 checked:bg-sky-500/20 transition-all cursor-pointer shrink-0 mt-0.5"
          :class="{ 'opacity-40': task.done }"
        />
        <span
          class="text-sm leading-snug"
          :class="task.done ? 'line-through text-zinc-600' : 'text-zinc-200'"
        >{{ task.text }}</span>
      </div>
      <div
        v-if="tasks.length === 0"
        class="flex flex-col items-center justify-center py-12 text-zinc-600"
      >
        <span class="text-2xl mb-2 opacity-30">◇</span>
        <p class="text-sm">No tasks yet</p>
        <p class="text-xs text-zinc-700 mt-1">Type something above to get started</p>
      </div>
    </div>

    <footer class="flex-none flex items-center justify-between pt-3 mt-3 border-t border-zinc-700/50 text-[11px] text-zinc-600">
      <span>{{ tasks.length }} task{{ tasks.length !== 1 ? 's' : '' }}</span>
      <span class="text-zinc-700">Ctrl+Enter to submit</span>
    </footer>
  </div>

  <!-- Light theme -->
  <div
    v-else
    class="h-screen w-screen bg-white/95 text-zinc-800 p-5 flex flex-col overflow-hidden select-none"
  >
    <header class="flex-none flex items-center justify-between pb-3 mb-3 border-b border-zinc-200/80">
      <div>
        <h1 class="text-base font-semibold tracking-wider text-zinc-800">
          <span class="text-sky-500">◆</span> DISPATCH
        </h1>
        <p class="text-[11px] text-zinc-400">ai-powered task hud</p>
      </div>
      <button
        @click="toggleTheme"
        class="text-[11px] text-zinc-400 hover:text-zinc-600 transition-colors px-2 py-1 rounded hover:bg-zinc-100 flex items-center gap-1.5"
        title="Switch to dark theme"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
        </svg>
      </button>
    </header>

    <div class="flex-none mb-4">
      <textarea
        v-model="brainDump"
        @keydown.ctrl.enter="handleDump"
        placeholder="Brain dump here... (Ctrl+Enter to submit)"
        class="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-3 text-sm text-zinc-700 placeholder-zinc-400 resize-none focus:outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-400/20 transition-all"
        rows="3"
      />
      <div class="flex gap-2 mt-2">
        <button
          @click="toggleMic"
          class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all"
          :class="isListening
            ? 'bg-red-500/10 text-red-600 border border-red-500/30 animate-pulse'
            : 'bg-zinc-100 text-zinc-500 border border-zinc-200 hover:text-zinc-700 hover:border-zinc-300'"
          :title="isListening ? 'Stop recording' : 'Start voice input'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="2" width="6" height="11" rx="3"/>
            <path d="M5 10a7 7 0 0114 0"/>
            <path d="M12 19v3M8 22h8"/>
          </svg>
          {{ isListening ? 'Listening...' : 'Voice' }}
        </button>
        <button
          @click="handleDump"
          class="text-xs bg-sky-500 text-white px-3 py-1.5 rounded-md hover:bg-sky-600 active:bg-sky-700 transition-all shadow-sm"
        >
          + Add Task
        </button>
        <button
          v-if="tasks.some(t => t.done)"
          @click="clearDone"
          class="text-xs text-zinc-500 border border-zinc-200 px-3 py-1.5 rounded-md hover:text-zinc-700 hover:border-zinc-300 transition-all"
        >
          Clear done
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto space-y-0.5">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="flex items-center gap-3 px-3 py-2 rounded-md transition-all"
        :class="task.done ? 'bg-zinc-50/50' : 'hover:bg-zinc-50'"
      >
        <input
          type="checkbox"
          v-model="task.done"
          class="appearance-none w-4 h-4 rounded border-2 border-zinc-300 checked:border-sky-500 checked:bg-sky-500 transition-all cursor-pointer shrink-0 mt-0.5"
          :class="{ 'opacity-40': task.done }"
        />
        <span
          class="text-sm leading-snug"
          :class="task.done ? 'line-through text-zinc-400' : 'text-zinc-700'"
        >{{ task.text }}</span>
      </div>
      <div
        v-if="tasks.length === 0"
        class="flex flex-col items-center justify-center py-12 text-zinc-300"
      >
        <span class="text-2xl mb-2 opacity-40">◇</span>
        <p class="text-sm text-zinc-400">No tasks yet</p>
        <p class="text-xs text-zinc-300 mt-1">Type something above to get started</p>
      </div>
    </div>

    <footer class="flex-none flex items-center justify-between pt-3 mt-3 border-t border-zinc-200/80 text-[11px] text-zinc-400">
      <span>{{ tasks.length }} task{{ tasks.length !== 1 ? 's' : '' }}</span>
      <span class="text-zinc-300">Ctrl+Enter to submit</span>
    </footer>
  </div>
</template>