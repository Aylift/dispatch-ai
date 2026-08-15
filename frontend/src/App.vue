<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { checkHealth, withRetry, fetchTasks, createTask, parseTasks, updateTask, clearDoneTasks } from './api.js'
import { useVoice } from './useVoice.js'
import PriorityMeter from './components/PriorityMeter.vue'
import { invoke } from '@tauri-apps/api/core'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

const theme = ref('dark')
const brainDump = ref('')
const tasks = ref([])
const isListening = ref(false)
const isParsing = ref(false)
const selectedPriority = ref(3)
const sortMode = ref('priority') // 'priority' | 'created'

// Backend/DB connection state: 'loading' = connecting/retrying, 'ready' = up,
// 'error' = unreachable (backend or DB failed).
const appStatus = ref(isTauri ? 'loading' : 'ready')
const connectionError = ref('')
let watchdogTimer = null

const PRIORITIES = {
  1: { label: 'Critical', text: 'text-red-400', dot: 'bg-red-500', badge: 'bg-red-500/15 text-red-400 border-red-500/40' },
  2: { label: 'High', text: 'text-orange-400', dot: 'bg-orange-500', badge: 'bg-orange-500/15 text-orange-400 border-orange-500/40' },
  3: { label: 'Medium', text: 'text-yellow-400', dot: 'bg-yellow-500', badge: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/40' },
  4: { label: 'Low', text: 'text-sky-400', dot: 'bg-sky-500', badge: 'bg-sky-500/15 text-sky-400 border-sky-500/40' },
  5: { label: 'Optional', text: 'text-zinc-400', dot: 'bg-zinc-500', badge: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/40' },
}

const isDark = computed(() => theme.value === 'dark')

// Sort tasks: undone first, then by the current sort mode.
// 'priority': 1=highest first, then newest. 'created': newest first.
const sortedTasks = computed(() => {
  if (sortMode.value === 'created') {
    return [...tasks.value].sort((a, b) => {
      if (a.done !== b.done) return a.done ? 1 : -1
      if (a.created_at !== b.created_at) return new Date(b.created_at) - new Date(a.created_at)
      return b.id - a.id
    })
  }
  return [...tasks.value].sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1
    if (a.priority !== b.priority) return a.priority - b.priority
    return b.id - a.id
  })
})

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}

async function hideHud() {
  if (!isTauri) return
  try {
    await invoke('hide_window')
  } catch (err) {
    console.error('hide_window failed:', err)
  }
}

// Grab the backend log path (Tauri-only) so we can surface a real hint when
// the backend/DB won't come up.
async function getBackendLogPath() {
  if (!isTauri) return ''
  try {
    const r = await invoke('backend_status')
    return r?.log_path || ''
  } catch {
    return ''
  }
}

// ---- Connection / startup ------------------------------------------------
// Poll /health with backoff until the backend + DB are ready, then load tasks
// (also retried). Never silently give up: if it can't connect we show an error.
async function waitForBackend() {
  appStatus.value = 'loading'
  connectionError.value = ''
  try {
    await withRetry(async () => {
      const h = await checkHealth()
      if (!h.ok) throw new Error(`health ${h.status}`)
    }, { label: 'backend health', intervalMs: 1000, timeBudgetMs: 60000 })
    appStatus.value = 'ready'
  } catch (err) {
    appStatus.value = 'error'
    connectionError.value = 'Cannot reach the backend. Is the app / Python venv installed and did the service start?'
    if (isTauri) {
      const p = await getBackendLogPath()
      if (p) connectionError.value += `\nCheck the log:\n${p}`
    }
  }
}

async function loadTasks() {
  if (appStatus.value !== 'ready') return
  try {
    tasks.value = await withRetry(fetchTasks, { label: 'fetch tasks', intervalMs: 1000, timeBudgetMs: 30000 })
  } catch (err) {
    console.error('loadTasks failed:', err)
    // If the backend died after being ready, flip back to error (watchdog
    // below will try to recover).
    appStatus.value = 'error'
    connectionError.value = 'Lost connection to the backend. It will reconnect automatically.'
  }
}

// Try to (re)establish a healthy connection. Called on mount and by Retry.
async function connect() {
  await waitForBackend()
  if (appStatus.value === 'ready') await loadTasks()
}

// Watchdog: once we think we're disconnected, keep pinging /health in the
// background and auto-load tasks as soon as the backend comes back.
function startWatchdog() {
  stopWatchdog()
  watchdogTimer = setInterval(async () => {
    if (appStatus.value === 'ready') return
    let h
    try {
      h = await checkHealth()
    } catch {
      h = { ok: false }
    }
    if (h.ok && appStatus.value !== 'ready') {
      appStatus.value = 'ready'
      connectionError.value = ''
      await loadTasks() // repopulate once the DB is reachable again
    }
  }, 4000)
}
function stopWatchdog() {
  if (watchdogTimer) {
    clearInterval(watchdogTimer)
    watchdogTimer = null
  }
}

// ---- Task operations -----------------------------------------------------
async function handleDump() {
  if (!brainDump.value.trim()) return
  try {
    const task = await createTask(brainDump.value, selectedPriority.value)
    tasks.value.unshift(task)
    brainDump.value = ''
    selectedPriority.value = 3
  } catch (err) {
    console.error('add task failed:', err)
    connectionError.value = 'Could not add task — backend unreachable.'
    appStatus.value = 'error'
  }
}

async function handleParse() {
  if (!brainDump.value.trim() || isParsing.value) return
  isParsing.value = true
  try {
    const created = await parseTasks(brainDump.value)
    tasks.value.unshift(...created)
    brainDump.value = ''
    selectedPriority.value = 3
  } catch (err) {
    console.error('AI parse failed:', err)
    connectionError.value = 'AI organize failed — backend unreachable.'
    appStatus.value = 'error'
  } finally {
    isParsing.value = false
  }
}

async function toggleDone(task) {
  try {
    await updateTask(task.id, { done: task.done })
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

async function clearDone() {
  try {
    await clearDoneTasks()
    tasks.value = tasks.value.filter(t => !t.done)
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not clear done tasks — backend unreachable.'
    appStatus.value = 'error'
  }
}

async function changePriority(task, priority) {
  try {
    const updated = await updateTask(task.id, { priority })
    task.priority = updated.priority
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not change priority — backend unreachable.'
    appStatus.value = 'error'
  }
}

const voiceBase = ref('')  // text already in the box when a voice session starts

const voice = useVoice({
  onInterim(text) {
    brainDump.value = voiceBase.value
      ? `${voiceBase.value} ${text}`.trim()
      : text
  },
  onStop() {
    isListening.value = false
    voiceBase.value = ''
  },
  onIdleStop() {
    isListening.value = false
    voiceBase.value = ''
  },
  onError(err) {
    isListening.value = false
    voiceBase.value = ''
    console.error('Voice transcription failed:', err)
    window.alert('Voice transcription failed. Check your connection and try again.')
  },
})

function toggleMic() {
  if (isListening.value) {
    voice.stop()
    isListening.value = false
    voiceBase.value = ''
  } else {
    voiceBase.value = brainDump.value
    voice.start()
    isListening.value = true
  }
}

function onTextareaKeydown(event) {
  if (event.key === 'Enter' && !event.ctrlKey && !event.metaKey && isListening.value) {
    event.preventDefault()
    toggleMic()
  }
}

onMounted(async () => {
  startWatchdog()
  await connect()
})

onUnmounted(() => {
  stopWatchdog()
})
</script>
<template>
  <!-- Dark theme -->
  <div
    v-if="isDark"
    class="h-screen w-screen bg-zinc-900/95 text-zinc-100 p-5 flex flex-col overflow-hidden select-none"
  >
    <header class="flex-none flex items-center justify-between pb-3 mb-3 border-b border-zinc-700/50" data-tauri-drag-region>
      <div>
        <h1 class="text-base font-semibold tracking-wider text-zinc-100">
          <span class="text-sky-400">&#9670;</span> DISPATCH
        </h1>
        <p class="text-[11px] text-zinc-500">ai-powered task hud</p>
      </div>
      <div v-if="appStatus !== 'ready'" class="flex items-center gap-2">
        <span
          v-if="appStatus === 'loading'"
          class="inline-flex items-center gap-1.5 text-[11px] text-amber-400/90"
        >
          <svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
          </svg>
          Loading…
        </span>
        <span
          v-else-if="appStatus === 'error'"
          class="inline-flex items-center gap-1.5 text-[11px] text-red-400/90"
          title="Click to retry connecting"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M10.29 3.86 1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          Offline
        </span>
      </div>
      <div class="flex items-center">
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
        <button
          v-if="isTauri"
          @click="hideHud"
          class="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-800 flex items-center gap-1.5 ml-2 pl-2 border-l border-zinc-700/50"
          title="Hide HUD (restore from the system tray)"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M5 18.5h14"/>
          </svg>
        </button>
      </div>
    </header>

    <div v-if="appStatus === 'error'" class="flex-none mb-3 px-3 py-2 rounded-md bg-red-500/10 border border-red-500/30 text-[12px] text-red-400">
      <p class="font-medium mb-1">Connection problem — backend / database unreachable.</p>
      <p class="text-[11px] text-red-400/70 whitespace-pre-line">{{ connectionError }}</p>
      <button
        @click="connect"
        class="mt-2 text-[11px] px-2.5 py-1 rounded border border-red-500/40 text-red-400 hover:bg-red-500/20 transition-colors"
      >Retry now</button>
    </div>
    <div v-else-if="appStatus === 'loading'" class="flex-none mb-3 px-3 py-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-400/90">
      Starting backend and loading your tasks…
    </div>

    <div class="flex-none mb-4">
      <div class="flex items-center gap-3">
        <textarea
          v-model="brainDump"
          @keydown.ctrl.enter="handleDump"
          @keydown="onTextareaKeydown"
          placeholder="Brain dump here... (Ctrl+Enter to submit)"
          class="flex-1 bg-zinc-800/80 border border-zinc-700/60 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-500 resize-none focus:outline-none focus:border-sky-500/50 focus:ring-1 focus:ring-sky-500/20 transition-all"
          rows="3"
        />
        <div class="flex flex-col items-center gap-1.5 shrink-0">
          <span class="text-[9px] uppercase tracking-widest text-zinc-500">Priority</span>
          <PriorityMeter v-model="selectedPriority" size="sm" :light="false" />
          <span class="text-[10px] font-medium" :class="PRIORITIES[selectedPriority]?.text">
            {{ PRIORITIES[selectedPriority]?.label }}
          </span>
        </div>
      </div>
      <div v-if="isListening" class="text-[11px] text-red-400/80 mt-1.5 mb-1 animate-pulse">
        &#9679; Listening — tap the mic or press Enter when done
      </div>
      <div class="flex gap-2 mt-2">
        <button
          @click="toggleMic"
          class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all"
          :class="isListening
            ? 'bg-red-500/20 text-red-400 border border-red-500/40 animate-pulse'
            : 'bg-zinc-800 text-zinc-400 border border-zinc-700/50 hover:text-zinc-200 hover:border-zinc-600'"
          :title="isListening ? 'Tap to stop recording' : 'Start voice input'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="2" width="6" height="11" rx="3"/>
            <path d="M5 10a7 7 0 0114 0"/>
            <path d="M12 19v3M8 22h8"/>
          </svg>
          {{ isListening ? 'Tap to stop' : 'Voice' }}
        </button>
        <button
          @click="handleParse"
          :disabled="isParsing"
          class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          :class="isParsing
            ? 'bg-violet-500/20 text-violet-400 border border-violet-500/40 animate-pulse'
            : 'bg-violet-500/10 text-violet-400 border border-violet-500/30 hover:bg-violet-500/20'"
          title="Let AI split this into prioritized tasks"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z"/>
            <path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"/>
          </svg>
          {{ isParsing ? 'Parsing...' : 'Organize' }}
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

    <div class="flex-1 overflow-y-auto">
      <TransitionGroup name="list" tag="div" class="space-y-0.5">
        <div
          v-for="task in sortedTasks"
          :key="task.id"
          data-testid="task-row"
          class="flex items-center gap-3 px-3 py-2 rounded-md transition-all cursor-default"
          :class="task.done ? 'bg-zinc-800/30' : 'hover:bg-zinc-800/50'"
        >
          <input
            type="checkbox"
            :checked="task.done"
            @change="task.done = !task.done; toggleDone(task)"
            class="appearance-none w-4 h-4 rounded border-2 border-zinc-600 checked:border-sky-500 checked:bg-sky-500/20 transition-all cursor-pointer shrink-0 mt-0.5"
            :class="{ 'opacity-40': task.done }"
          />
          <div class="flex-1 flex items-center gap-2 min-w-0">
            <span
              class="text-sm leading-snug flex-1 truncate"
              :class="task.done ? 'line-through text-zinc-600' : 'text-zinc-200'"
            >{{ task.text }}</span>
            <PriorityMeter
              :modelValue="task.priority"
              size="xs"
              :light="!isDark"
              @update:modelValue="changePriority(task, $event)"
            />
          </div>
        </div>
      </TransitionGroup>
      <div v-if="appStatus==='ready' && tasks.length === 0" class="flex flex-col items-center justify-center py-12 text-zinc-600">
        <span class="text-2xl mb-2 opacity-30">&#9670;</span>
        <p class="text-sm">No tasks yet</p>
        <p class="text-xs text-zinc-700 mt-1">Type something above to get started</p>
      </div>
      <div class="flex items-center justify-center gap-1 pt-3 pb-1 text-[11px]">
        <span class="text-zinc-500 mr-1">sort</span>
        <button
          data-testid="sort-priority"
          @click="sortMode = 'priority'"
          class="px-1.5 py-0.5 rounded transition-colors"
          :class="sortMode === 'priority' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
        >Priority</button>
        <button
          data-testid="sort-created"
          @click="sortMode = 'created'"
          class="px-1.5 py-0.5 rounded transition-colors"
          :class="sortMode === 'created' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
        >Created</button>
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
    <header class="flex-none flex items-center justify-between pb-3 mb-3 border-b border-zinc-200/80" data-tauri-drag-region>
      <div>
        <h1 class="text-base font-semibold tracking-wider text-zinc-800">
          <span class="text-sky-500">&#9670;</span> DISPATCH
        </h1>
        <p class="text-[11px] text-zinc-400">ai-powered task hud</p>
      </div>
      <div v-if="appStatus !== 'ready'" class="flex items-center gap-2">
        <span
          v-if="appStatus === 'loading'"
          class="inline-flex items-center gap-1.5 text-[11px] text-amber-500/90"
        >
          <svg class="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
          </svg>
          Loading…
        </span>
        <span
          v-else-if="appStatus === 'error'"
          class="inline-flex items-center gap-1.5 text-[11px] text-red-500/90"
          title="Click to retry connecting"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M10.29 3.86 1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          Offline
        </span>
      </div>
      <div class="flex items-center">
        <button
          @click="toggleTheme"
          class="text-[11px] text-zinc-400 hover:text-zinc-600 transition-colors px-2 py-1 rounded hover:bg-zinc-100 flex items-center gap-1.5"
          title="Switch to dark theme"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
          </svg>
        </button>
        <button
          v-if="isTauri"
          @click="hideHud"
          class="text-[11px] text-zinc-400 hover:text-zinc-600 transition-colors px-2 py-1 rounded hover:bg-zinc-100 flex items-center gap-1.5 ml-2 pl-2 border-l border-zinc-200"
          title="Hide HUD (restore from the system tray)"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M5 18.5h14"/>
          </svg>
        </button>
      </div>
    </header>

    <div v-if="appStatus === 'error'" class="flex-none mb-3 px-3 py-2 rounded-md bg-red-500/10 border border-red-500/30 text-[12px] text-red-500">
      <p class="font-medium mb-1">Connection problem — backend / database unreachable.</p>
      <p class="text-[11px] text-red-500/70 whitespace-pre-line">{{ connectionError }}</p>
      <button
        @click="connect"
        class="mt-2 text-[11px] px-2.5 py-1 rounded border border-red-500/40 text-red-500 hover:bg-red-500/10 transition-colors"
      >Retry now</button>
    </div>
    <div v-else-if="appStatus === 'loading'" class="flex-none mb-3 px-3 py-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-[11px] text-amber-500/90">
      Starting backend and loading your tasks…
    </div>

    <div class="flex-none mb-4">
      <div class="flex items-center gap-3">
        <textarea
          v-model="brainDump"
          @keydown.ctrl.enter="handleDump"
          @keydown="onTextareaKeydown"
          placeholder="Brain dump here... (Ctrl+Enter to submit)"
          class="flex-1 bg-zinc-50 border border-zinc-200 rounded-lg p-3 text-sm text-zinc-700 placeholder-zinc-400 resize-none focus:outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-400/20 transition-all"
          rows="3"
        />
        <div class="flex flex-col items-center gap-1.5 shrink-0">
          <span class="text-[9px] uppercase tracking-widest text-zinc-400">Priority</span>
          <PriorityMeter v-model="selectedPriority" size="sm" :light="true" />
          <span class="text-[10px] font-medium" :class="PRIORITIES[selectedPriority]?.text">
            {{ PRIORITIES[selectedPriority]?.label }}
          </span>
        </div>
      </div>
      <div v-if="isListening" class="text-[11px] text-red-500/80 mt-1.5 mb-1 animate-pulse">
        &#9679; Listening — tap the mic or press Enter when done
      </div>
      <div class="flex gap-2 mt-2">
        <button
          @click="toggleMic"
          class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all"
          :class="isListening
            ? 'bg-red-500/10 text-red-600 border border-red-500/30 animate-pulse'
            : 'bg-zinc-100 text-zinc-500 border border-zinc-200 hover:text-zinc-700 hover:border-zinc-300'"
          :title="isListening ? 'Tap to stop recording' : 'Start voice input'"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="2" width="6" height="11" rx="3"/>
            <path d="M5 10a7 7 0 0114 0"/>
            <path d="M12 19v3M8 22h8"/>
          </svg>
          {{ isListening ? 'Tap to stop' : 'Voice' }}
        </button>
        <button
          @click="handleParse"
          :disabled="isParsing"
          class="text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          :class="isParsing
            ? 'bg-violet-500/10 text-violet-600 border border-violet-500/30 animate-pulse'
            : 'bg-violet-500/10 text-violet-600 border border-violet-500/30 hover:bg-violet-500/20'"
          title="Let AI split this into prioritized tasks"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2z"/>
            <path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"/>
          </svg>
          {{ isParsing ? 'Parsing...' : 'Organize' }}
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

    <div class="flex-1 overflow-y-auto">
      <TransitionGroup name="list" tag="div" class="space-y-0.5">
        <div
          v-for="task in sortedTasks"
          :key="task.id"
          data-testid="task-row"
          class="flex items-center gap-3 px-3 py-2 rounded-md transition-all"
          :class="task.done ? 'bg-zinc-50/50' : 'hover:bg-zinc-50'"
        >
          <input
            type="checkbox"
            :checked="task.done"
            @change="task.done = !task.done; toggleDone(task)"
            class="appearance-none w-4 h-4 rounded border-2 border-zinc-300 checked:border-sky-500 checked:bg-sky-500 transition-all cursor-pointer shrink-0 mt-0.5"
            :class="{ 'opacity-40': task.done }"
          />
          <div class="flex-1 flex items-center gap-2 min-w-0">
            <span
              class="text-sm leading-snug flex-1 truncate"
              :class="task.done ? 'line-through text-zinc-400' : 'text-zinc-700'"
            >{{ task.text }}</span>
            <PriorityMeter
              :modelValue="task.priority"
              size="xs"
              :light="!isDark"
              @update:modelValue="changePriority(task, $event)"
            />
          </div>
        </div>
      </TransitionGroup>
      <div v-if="appStatus==='ready' && tasks.length === 0" class="flex flex-col items-center justify-center py-12 text-zinc-300">
        <span class="text-2xl mb-2 opacity-40">&#9670;</span>
        <p class="text-sm text-zinc-400">No tasks yet</p>
        <p class="text-xs text-zinc-300 mt-1">Type something above to get started</p>
      </div>
      <div class="flex items-center justify-center gap-1 pt-3 pb-1 text-[11px]">
        <span class="text-zinc-400 mr-1">sort</span>
        <button
          data-testid="sort-priority"
          @click="sortMode = 'priority'"
          class="px-1.5 py-0.5 rounded transition-colors"
          :class="sortMode === 'priority' ? 'bg-zinc-200 text-zinc-700' : 'text-zinc-400 hover:text-zinc-600'"
        >Priority</button>
        <button
          data-testid="sort-created"
          @click="sortMode = 'created'"
          class="px-1.5 py-0.5 rounded transition-colors"
          :class="sortMode === 'created' ? 'bg-zinc-200 text-zinc-700' : 'text-zinc-400 hover:text-zinc-600'"
        >Created</button>
      </div>
    </div>

    <footer class="flex-none flex items-center justify-between pt-3 mt-3 border-t border-zinc-200/80 text-[11px] text-zinc-400">
      <span>{{ tasks.length }} task{{ tasks.length !== 1 ? 's' : '' }}</span>
      <span class="text-zinc-300">Ctrl+Enter to submit</span>
    </footer>
  </div>
</template>