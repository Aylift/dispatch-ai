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
const view = ref('today')        // 'all' | 'today' — which tab is shown (TODAY is default)
const TODAY_TAG = 'TODAY'
const RECURRING_TAG = 'RECURRING'
const expandedId = ref(null)     // task id currently expanded (detail panel)
const descDraft = ref('')        // draft description while editing
const editingId = ref(null)      // task id currently in title-edit mode
const editingText = ref('')      // draft text while editing
let descInputEl = null
let editInputEl = null

// Transient undo state for the Today / Recur toggles. When one is clicked the
// change applies optimistically and the button turns into a countdown with a
// reverse arrow; if the user doesn't cancel within the window it commits to the
// backend. This stops a mis-click from yanking a task out of the current tab.
const undo = ref(null) // { taskId, action, remaining, timer, revert, commit }

function cancelUndo() {
  if (undo.value) {
    clearInterval(undo.value.timer)
    undo.value = null
  }
}

function startUndo(taskId, action, revert, commit, seconds = 3) {
  cancelUndo()
  const timer = setInterval(() => {
    const u = undo.value
    if (!u) return
    u.remaining -= 1
    if (u.remaining <= 0) {
      clearInterval(u.timer)
      undo.value = null
      u.commit()
    }
  }, 1000)
  undo.value = { taskId, action, remaining: seconds, timer, revert, commit }
}

function undoNow() {
  if (undo.value) {
    clearInterval(undo.value.timer)
    undo.value.revert()
    undo.value = null
  }
}

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
const hasTag = (task, tag) => Array.isArray(task.tags) && task.tags.includes(tag)

// A task with a pending undo stays in the TODAY tab even if it just lost its
// TODAY tag, so the reverse-arrow button remains clickable instead of the row
// vanishing to the All list mid-countdown.
const hasPendingUndo = (taskId) => undo.value && undo.value.taskId === taskId

// Tasks shown in the active tab. 'today' filters to tasks tagged TODAY, plus
// any task still inside its undo window so the revert button stays visible.
const visibleTasks = computed(() => {
  if (view.value === 'today') return sortedTasks.value.filter(t => hasTag(t, TODAY_TAG) || hasPendingUndo(t.id))
  return sortedTasks.value
})

// In the TODAY tab, recurring tasks float to the top, separated from the
// normal today tasks by a divider.
const todayRecurring = computed(() =>
  visibleTasks.value.filter(t => t.recurring)
)
const todayNormal = computed(() =>
  visibleTasks.value.filter(t => !t.recurring)
)

// Flat list for the TODAY tab: recurring tasks, then a divider, then normal.
const todayList = computed(() => {
  const items = []
  for (const t of todayRecurring.value) items.push({ type: 'task', task: t })
  if (todayRecurring.value.length && todayNormal.value.length) items.push({ type: 'divider' })
  for (const t of todayNormal.value) items.push({ type: 'task', task: t })
  return items
})

// List actually rendered: TODAY tab uses the grouped list, All uses everything.
const renderList = computed(() =>
  view.value === 'today' ? todayList.value : visibleTasks.value.map(t => ({ type: 'task', task: t }))
)

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

// Toggle the TODAY tag on a task. It stays in the main list but also appears
// in the TODAY tab. Applies optimistically and offers a 3s undo window so a
// mis-click doesn't yank the task out of the current tab.
function toggleToday(task) {
  const prevTags = task.tags || []
  const had = hasTag(task, TODAY_TAG)
  const newTags = had
    ? prevTags.filter(t => t !== TODAY_TAG)
    : [...prevTags, TODAY_TAG]
  task.tags = newTags
  startUndo(
    task.id, 'today',
    () => { task.tags = prevTags },
    async () => {
      try {
        const updated = await updateTask(task.id, { tags: newTags })
        task.tags = updated.tags
      } catch (err) {
        console.error(err)
        task.tags = prevTags
      }
    },
    3
  )
}

// Toggle the recurring flag. Recurring tasks always carry the TODAY tag so they
// show up in the TODAY tab and reset daily on the backend. Same 3s undo window.
function toggleRecurring(task) {
  const prevRecurring = task.recurring
  const prevTags = task.tags || []
  const recurring = !prevRecurring
  let newTags = prevTags
  if (recurring && !hasTag(task, TODAY_TAG)) newTags = [...newTags, TODAY_TAG]
  if (!recurring) newTags = newTags.filter(t => t !== RECURRING_TAG)
  task.recurring = recurring
  task.tags = newTags
  startUndo(
    task.id, 'recurring',
    () => { task.recurring = prevRecurring; task.tags = prevTags },
    async () => {
      try {
        const updated = await updateTask(task.id, { recurring, tags: newTags })
        task.recurring = updated.recurring
        task.tags = updated.tags
      } catch (err) {
        console.error(err)
        task.recurring = prevRecurring
        task.tags = prevTags
      }
    },
    3
  )
}

// ---- Task detail expansion (single-click on the row) ---------------------
// Clicking a task toggles an inline detail panel with the description editor.
// The title is edited in place (single-click on the title), so there is no
// duplicate title inside the panel and no click/dblclick ambiguity.
function toggleExpand(task) {
  if (expandedId.value === task.id) {
    expandedId.value = null
    return
  }
  expandedId.value = task.id
  descDraft.value = task.description || ''
  requestAnimationFrame(() => {
    if (descInputEl) descInputEl.focus()
  })
}

async function saveDescription(task) {
  const desc = descDraft.value.trim()
  if (desc === (task.description || '')) return
  try {
    const updated = await updateTask(task.id, { description: desc || null })
    task.description = updated.description
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

// ---- Task title editing (single-click, in place) ------------------------
function startEdit(task) {
  editingId.value = task.id
  editingText.value = task.text
  // Focus + select after the input renders.
  requestAnimationFrame(() => {
    if (editInputEl) {
      editInputEl.focus()
      editInputEl.select()
    }
  })
}

function cancelEdit() {
  editingId.value = null
  editingText.value = ''
}

async function saveEdit(task) {
  const text = editingText.value.trim()
  cancelEdit()
  if (!text || text === task.text) return
  try {
    const updated = await updateTask(task.id, { text })
    task.text = updated.text
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

const voiceBase = ref('')  // text already in the box when a voice session starts

const mics = ref([])          // available audio input devices
const selectedMicId = ref('') // '' = system default

async function loadMics() {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices()
    // Windows exposes the same physical mic multiple times (Default,
    // Communications, raw device). Deduplicate by groupId so each real
    // microphone appears once.
    const seen = new Set()
    mics.value = devices.filter(d => {
      if (d.kind !== 'audioinput') return false
      const key = d.groupId || d.deviceId
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    // Keep the previous selection if it still exists, else default.
    if (!mics.value.some(d => d.deviceId === selectedMicId.value)) {
      selectedMicId.value = mics.value[0]?.deviceId || ''
    }
  } catch {
    mics.value = []
  }
}

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
    voice.start(selectedMicId.value)
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
  loadMics()
})

onUnmounted(() => {
  stopWatchdog()
})
</script>
<template>
  <!-- Dark theme -->
  <div
    v-if="isDark"
    class="h-full w-full bg-zinc-900/95 text-zinc-100 p-5 flex flex-col overflow-hidden select-none"
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
          data-testid="task-input"
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
        <select
          v-if="mics.length > 1"
          v-model="selectedMicId"
          :disabled="isListening"
          class="text-xs px-2 py-1.5 rounded-md bg-zinc-800 text-zinc-400 border border-zinc-700/50 hover:border-zinc-600 disabled:opacity-40 max-w-[140px]"
          title="Choose microphone"
        >
          <option v-for="m in mics" :key="m.deviceId" :value="m.deviceId">
            {{ m.label || 'Microphone' }}
          </option>
        </select>
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
      <div class="flex items-center gap-1 mb-2 text-[11px]">
        <button
          data-testid="tab-today"
          @click="view = 'today'"
          class="px-2.5 py-1 rounded transition-colors cursor-pointer"
          :class="view === 'today' ? 'bg-sky-500/20 text-sky-300' : 'text-zinc-500 hover:text-zinc-300'"
        >TODAY</button>
        <button
          data-testid="tab-all"
          @click="view = 'all'"
          class="px-2.5 py-1 rounded transition-colors cursor-pointer"
          :class="view === 'all' ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
        >All</button>
      </div>
      <TransitionGroup name="list" tag="div" class="space-y-0.5">
        <template v-for="item in renderList" :key="item.type === 'divider' ? 'recurring-divider' : item.task.id">
          <div
            v-if="item.type === 'divider'"
            class="flex items-center gap-2 my-1.5 px-1"
          >
            <span class="text-[9px] uppercase tracking-widest text-violet-400/80 shrink-0">Recurring</span>
            <span class="flex-1 h-px bg-gradient-to-r from-violet-500/50 via-violet-500/20 to-transparent"></span>
          </div>
          <div v-else class="rounded-md">
          <div
            data-testid="task-row"
            class="flex items-center gap-3 px-3 py-2 rounded-md transition-all"
            :class="item.task.done ? 'bg-zinc-800/30' : 'hover:bg-zinc-800/50'"
          >
            <input
              type="checkbox"
              :checked="item.task.done"
              @click.stop
              @change="item.task.done = !item.task.done; toggleDone(item.task)"
              class="appearance-none w-4 h-4 rounded border-2 border-zinc-600 checked:border-sky-500 checked:bg-sky-500/20 transition-all cursor-pointer shrink-0 mt-0.5"
              :class="{ 'opacity-40': item.task.done }"
            />
            <div class="flex-1 flex items-center gap-2 min-w-0">
              <input
                v-if="editingId === item.task.id"
                ref="editInputEl"
                v-model="editingText"
                data-testid="task-title-input"
                @click.stop
                @keydown.enter="saveEdit(item.task)"
                @keydown.esc="cancelEdit"
                @blur="saveEdit(item.task)"
                class="flex-1 min-w-0 text-sm leading-snug bg-zinc-900 border border-sky-500/60 rounded px-1.5 py-0.5 text-zinc-100 focus:outline-none"
              />
              <span
                v-else
                @click.stop="startEdit(item.task)"
                class="text-sm leading-snug flex-1 truncate cursor-text"
                :class="item.task.done ? 'line-through text-zinc-600' : 'text-zinc-200'"
                :title="'Click to edit title'"
              >{{ item.task.text }}</span>
              <PriorityMeter
                :modelValue="item.task.priority"
                size="xs"
                :light="!isDark"
                @click.stop
                @update:modelValue="changePriority(item.task, $event)"
              />
              <button
                v-if="undo && undo.taskId === item.task.id && undo.action === 'today'"
                data-testid="undo-today"
                @click.stop="undoNow()"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer bg-amber-500/20 text-amber-300 border-amber-500/40"
                title="Undo — click to cancel"
              >↩ {{ undo.remaining }}s</button>
              <button
                v-else
                data-testid="toggle-today"
                @click.stop="toggleToday(item.task)"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer"
                :class="hasTag(item.task, TODAY_TAG)
                  ? 'bg-sky-500/20 text-sky-300 border-sky-500/40'
                  : 'text-zinc-500 border-zinc-700/50 hover:text-sky-300 hover:border-sky-500/40'"
                :title="hasTag(item.task, TODAY_TAG) ? 'Remove from today' : 'Add to today'"
              >Today</button>
              <button
                v-if="undo && undo.taskId === item.task.id && undo.action === 'recurring'"
                data-testid="undo-recurring"
                @click.stop="undoNow()"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer bg-amber-500/20 text-amber-300 border-amber-500/40"
                title="Undo — click to cancel"
              >↩ {{ undo.remaining }}s</button>
              <button
                v-else
                data-testid="toggle-recurring"
                @click.stop="toggleRecurring(item.task)"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer"
                :class="item.task.recurring
                  ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
                  : 'text-zinc-500 border-zinc-700/50 hover:text-violet-300 hover:border-violet-500/40'"
                :title="item.task.recurring ? 'Remove recurring' : 'Make recurring (resets daily)'"
              >{{ item.task.recurring ? '⟳' : 'Recur' }}</button>
              <button
                data-testid="task-expand"
                @click.stop="toggleExpand(item.task)"
                class="text-zinc-500 hover:text-sky-300 transition-colors shrink-0 cursor-pointer px-0.5"
                :title="expandedId === item.task.id ? 'Collapse' : 'Expand'"
              >{{ expandedId === item.task.id ? '▾' : '▸' }}</button>
            </div>
          </div>
          <div
            v-if="expandedId === item.task.id"
            data-testid="task-detail"
            class="ml-9 mr-3 mb-1 px-3 py-2 rounded-md bg-zinc-900/60 border border-zinc-700/40"
          >
            <div class="flex items-center gap-2 mb-1.5 text-[10px] text-zinc-500">
              <span v-for="tag in (item.task.tags || [])" :key="tag" class="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">{{ tag === TODAY_TAG ? 'Today' : tag }}</span>
              <span v-if="!(item.task.tags || []).length" class="italic">no tags</span>
            </div>
            <textarea
              ref="descInputEl"
              v-model="descDraft"
              data-testid="task-description-input"
              @blur="saveDescription(item.task)"
              placeholder="Add a description..."
              class="w-full bg-zinc-900 border border-zinc-700/60 rounded p-2 text-xs text-zinc-200 placeholder-zinc-600 resize-none focus:outline-none focus:border-sky-500/50"
              rows="3"
            ></textarea>
          </div>
          </div>
          </template>
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
    class="h-full w-full bg-white/95 text-zinc-800 p-5 flex flex-col overflow-hidden select-none"
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
          data-testid="task-input"
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
        <select
          v-if="mics.length > 1"
          v-model="selectedMicId"
          :disabled="isListening"
          class="text-xs px-2 py-1.5 rounded-md bg-zinc-100 text-zinc-500 border border-zinc-200 hover:border-zinc-300 disabled:opacity-40 max-w-[140px]"
          title="Choose microphone"
        >
          <option v-for="m in mics" :key="m.deviceId" :value="m.deviceId">
            {{ m.label || 'Microphone' }}
          </option>
        </select>
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
      <div class="flex items-center gap-1 mb-2 text-[11px]">
        <button
          data-testid="tab-today"
          @click="view = 'today'"
          class="px-2.5 py-1 rounded transition-colors cursor-pointer"
          :class="view === 'today' ? 'bg-sky-500/15 text-sky-600' : 'text-zinc-400 hover:text-zinc-600'"
        >TODAY</button>
        <button
          data-testid="tab-all"
          @click="view = 'all'"
          class="px-2.5 py-1 rounded transition-colors cursor-pointer"
          :class="view === 'all' ? 'bg-zinc-200 text-zinc-700' : 'text-zinc-400 hover:text-zinc-600'"
        >All</button>
      </div>
      <TransitionGroup name="list" tag="div" class="space-y-0.5">
        <template v-for="item in renderList" :key="item.type === 'divider' ? 'recurring-divider' : item.task.id">
          <div
            v-if="item.type === 'divider'"
            class="flex items-center gap-2 my-1.5 px-1"
          >
            <span class="text-[9px] uppercase tracking-widest text-violet-500/80 shrink-0">Recurring</span>
            <span class="flex-1 h-px bg-gradient-to-r from-violet-500/50 via-violet-500/20 to-transparent"></span>
          </div>
          <div v-else class="rounded-md">
          <div
            data-testid="task-row"
            class="flex items-center gap-3 px-3 py-2 rounded-md transition-all"
            :class="item.task.done ? 'bg-zinc-50/50' : 'hover:bg-zinc-50'"
          >
            <input
              type="checkbox"
              :checked="item.task.done"
              @click.stop
              @change="item.task.done = !item.task.done; toggleDone(item.task)"
              class="appearance-none w-4 h-4 rounded border-2 border-zinc-300 checked:border-sky-500 checked:bg-sky-500 transition-all cursor-pointer shrink-0 mt-0.5"
              :class="{ 'opacity-40': item.task.done }"
            />
            <div class="flex-1 flex items-center gap-2 min-w-0">
              <input
                v-if="editingId === item.task.id"
                ref="editInputEl"
                v-model="editingText"
                data-testid="task-title-input"
                @click.stop
                @keydown.enter="saveEdit(item.task)"
                @keydown.esc="cancelEdit"
                @blur="saveEdit(item.task)"
                class="flex-1 min-w-0 text-sm leading-snug bg-white border border-sky-400/70 rounded px-1.5 py-0.5 text-zinc-800 focus:outline-none"
              />
              <span
                v-else
                @click.stop="startEdit(item.task)"
                class="text-sm leading-snug flex-1 truncate cursor-text"
                :class="item.task.done ? 'line-through text-zinc-400' : 'text-zinc-700'"
                :title="'Click to edit title'"
              >{{ item.task.text }}</span>
              <PriorityMeter
                :modelValue="item.task.priority"
                size="xs"
                :light="!isDark"
                @click.stop
                @update:modelValue="changePriority(item.task, $event)"
              />
              <button
                v-if="undo && undo.taskId === item.task.id && undo.action === 'today'"
                data-testid="undo-today"
                @click.stop="undoNow()"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer bg-amber-500/20 text-amber-600 border-amber-500/40"
                title="Undo — click to cancel"
              >↩ {{ undo.remaining }}s</button>
              <button
                v-else
                data-testid="toggle-today"
                @click.stop="toggleToday(item.task)"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer"
                :class="hasTag(item.task, TODAY_TAG)
                  ? 'bg-sky-500/15 text-sky-600 border-sky-500/40'
                  : 'text-zinc-400 border-zinc-200 hover:text-sky-600 hover:border-sky-400/50'"
                :title="hasTag(item.task, TODAY_TAG) ? 'Remove from today' : 'Add to today'"
              >Today</button>
              <button
                v-if="undo && undo.taskId === item.task.id && undo.action === 'recurring'"
                data-testid="undo-recurring"
                @click.stop="undoNow()"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer bg-amber-500/20 text-amber-600 border-amber-500/40"
                title="Undo — click to cancel"
              >↩ {{ undo.remaining }}s</button>
              <button
                v-else
                data-testid="toggle-recurring"
                @click.stop="toggleRecurring(item.task)"
                class="text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer"
                :class="item.task.recurring
                  ? 'bg-violet-500/15 text-violet-600 border-violet-500/40'
                  : 'text-zinc-400 border-zinc-200 hover:text-violet-600 hover:border-violet-400/50'"
                :title="item.task.recurring ? 'Remove recurring' : 'Make recurring (resets daily)'"
              >{{ item.task.recurring ? '⟳' : 'Recur' }}</button>
              <button
                data-testid="task-expand"
                @click.stop="toggleExpand(item.task)"
                class="text-zinc-400 hover:text-sky-600 transition-colors shrink-0 cursor-pointer px-0.5"
                :title="expandedId === item.task.id ? 'Collapse' : 'Expand'"
              >{{ expandedId === item.task.id ? '▾' : '▸' }}</button>
            </div>
          </div>
          <div
            v-if="expandedId === item.task.id"
            data-testid="task-detail"
            class="ml-9 mr-3 mb-1 px-3 py-2 rounded-md bg-white border border-zinc-200"
          >
            <div class="flex items-center gap-2 mb-1.5 text-[10px] text-zinc-500">
              <span v-for="tag in (item.task.tags || [])" :key="tag" class="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-600 border border-sky-500/30">{{ tag === TODAY_TAG ? 'Today' : tag }}</span>
              <span v-if="!(item.task.tags || []).length" class="italic">no tags</span>
            </div>
            <textarea
              ref="descInputEl"
              v-model="descDraft"
              data-testid="task-description-input"
              @blur="saveDescription(item.task)"
              placeholder="Add a description..."
              class="w-full bg-zinc-50 border border-zinc-200 rounded p-2 text-xs text-zinc-700 placeholder-zinc-400 resize-none focus:outline-none focus:border-sky-400/60"
              rows="3"
            ></textarea>
          </div>
          </div>
          </template>
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