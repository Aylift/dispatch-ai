<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { checkHealth, withRetry, fetchTasks, createTask, parseTasks, updateTask, deleteTask, clearDoneTasks, fetchSettings, updateSettings } from './api.js'
import { useVoice } from './useVoice.js'
import PriorityMeter from './components/PriorityMeter.vue'
import AppIcon from './components/AppIcon.vue'
import { invoke } from '@tauri-apps/api/core'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

const theme = ref('dark')
const brainDump = ref('')
const tasks = ref([])
const isListening = ref(false)
const isParsing = ref(false)
const selectedPriority = ref(3)
const sortMode = ref('priority') // 'priority' | 'created'
// 0 = Priority, 1 = Created. Drives the sliding highlight pill between the
// sort buttons so switching modes glides instead of jumping.
const sortPillPos = computed(() => (sortMode.value === 'created' ? 1 : 0))
const view = ref('today')        // 'all' | 'today' — which tab is shown (TODAY is default)
const TODAY_TAG = 'TODAY'
const RECURRING_TAG = 'RECURRING'
const expandedId = ref(null)     // task id currently expanded (detail panel)
const descDraft = ref('')        // draft description while editing
const editingId = ref(null)      // task id currently in title-edit mode
const editingText = ref('')      // draft text while editing
let descInputEl = null
let editInputEl = null

// Global toast undo. An undoable action applies optimistically and shows a
// bottom toast with an explicit Undo button. If the user doesn't click Undo
// within the window, commit() runs; clicking Undo calls revert() and clears
// the toast. A new undoable action replaces the previous toast.
const undo = ref(null) // { taskId, action, message, timer, revert, commit }
const UNDO_MS = 5000

function cancelUndo() {
  if (undo.value) {
    clearTimeout(undo.value.timer)
    undo.value = null
  }
}

function startUndo(taskId, action, message, revert, commit) {
  cancelUndo()
  const timer = setTimeout(() => {
    const u = undo.value
    if (!u) return
    undo.value = null
    u.commit()
  }, UNDO_MS)
  undo.value = { taskId, action, message, timer, revert, commit }
}

function undoNow() {
  if (undo.value) {
    clearTimeout(undo.value.timer)
    undo.value.revert()
    undo.value = null
  }
}

// ---- Task overflow menu ---------------------------------------------------
// The "..." menu on each row holds the secondary actions (Today, Recur, Reset,
// Delete). Only one menu is open at a time; it closes on outside click, Escape,
// or after selecting an action. It must not trigger row expansion.
const menuOpenId = ref(null)

function toggleMenu(taskId) {
  menuOpenId.value = menuOpenId.value === taskId ? null : taskId
}

function closeMenu() {
  menuOpenId.value = null
}

// Close the open menu when clicking anywhere outside it. The menu button and
// the menu itself stop propagation so their own clicks don't close it.
function onDocClick() {
  closeMenu()
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

// Tasks shown in the active tab. 'today' filters to tasks tagged TODAY, plus
// any task still inside its undo window so the revert button stays visible.
const visibleTasks = computed(() => {
  if (view.value === 'today') return sortedTasks.value.filter(t => hasTag(t, TODAY_TAG) || hasPendingUndo(t.id))
  return sortedTasks.value
})

// In the TODAY tab, normal tasks come first, then a divider, then the
// recurring tasks below it.
const todayRecurring = computed(() =>
  visibleTasks.value.filter(t => t.recurring)
)
const todayNormal = computed(() =>
  visibleTasks.value.filter(t => !t.recurring)
)

// Flat list for the TODAY tab: normal tasks, then a divider, then recurring.
const todayList = computed(() => {
  const items = []
  for (const t of todayNormal.value) items.push({ type: 'task', task: t })
  if (todayRecurring.value.length && todayNormal.value.length) items.push({ type: 'divider' })
  for (const t of todayRecurring.value) items.push({ type: 'task', task: t })
  return items
})

// List actually rendered: TODAY tab uses the grouped list, All uses everything.
const fullList = computed(() =>
  view.value === 'today' ? todayList.value : visibleTasks.value.map(t => ({ type: 'task', task: t }))
)

// ---- Paging ---------------------------------------------------------------
// Customizable page size (persisted in the settings table). Paging is purely
// frontend: we slice the fully sorted/filtered list, so sorting, TODAY grouping
// and the recurring divider all keep working regardless of page size.
const PAGE_SIZE_OPTIONS = [5, 10, 25, 50]
const pageSize = ref(10)
const page = ref(1)

const totalPages = computed(() => Math.max(1, Math.ceil(fullList.value.length / pageSize.value)))
const renderList = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return fullList.value.slice(start, start + pageSize.value)
})

function setPageSize(size) {
  pageSize.value = size
  page.value = 1
  updateSettings({ page_size: size }).catch(err => console.error('save page size failed:', err))
}

async function loadSettings() {
  try {
    const s = await fetchSettings()
    if (s?.page_size) pageSize.value = s.page_size
  } catch (err) {
    console.error('loadSettings failed:', err)
  }
}

// If tasks are deleted/cleared and the current page no longer exists, fall back
// to the last valid page instead of showing an empty list.
watch(totalPages, (n) => {
  if (page.value > n) page.value = n
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
    const updated = await updateTask(task.id, { done: task.done })
    task.status = updated.status
    task.started_at = updated.started_at
    task.elapsed_seconds = updated.elapsed_seconds
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

// ---- Focus / timeboxing --------------------------------------------------
// Live clock tick so active tasks show a running elapsed timer. Re-renders the
// displayed elapsed time every second without touching the backend.
const nowTick = ref(Date.now())
let clockTimer = null
function startClock() {
  if (clockTimer) return
  clockTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
}
function stopClock() {
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
}

// Effective elapsed seconds for a task: accumulated + live running time.
function effectiveElapsed(task) {
  let base = task.elapsed_seconds || 0
  if (task.status === 'active' && task.started_at) {
    let iso = task.started_at
    // The backend stores started_at in UTC but SQLite returns it without a
    // timezone suffix. Treat a naive string as UTC so the live timer isn't
    // skewed by the local UTC offset (e.g. +2h in Warsaw).
    if (!/[zZ]|[+-]\d\d:\d\d$/.test(iso)) iso += 'Z'
    const started = new Date(iso).getTime()
    base += Math.max(0, Math.floor((nowTick.value - started) / 1000))
  }
  return base
}

function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`
  if (m > 0) return `${m}m ${String(sec).padStart(2, '0')}s`
  return `${sec}s`
}

// Compact "minutes elapsed / total minutes" label for the task row, e.g. "5/30m".
// Only shown when the task has a timebox and is active/paused.
function timeboxLabel(task) {
  const total = task.timebox_minutes
  if (!total) return null
  const elapsedMin = Math.floor(effectiveElapsed(task) / 60)
  return `${elapsedMin}/${total}m`
}

// Start / pause / resume a task. Starting auto-tags TODAY (backend does this
// too, but we mirror it optimistically). Pausing keeps the TODAY tag.
async function toggleFocus(task) {
  const next = task.status === 'active' ? 'paused' : 'active'
  const prev = { status: task.status, started_at: task.started_at, tags: task.tags || [] }
  // Optimistic update
  task.status = next
  if (next === 'active') {
    task.started_at = new Date().toISOString()
    if (!hasTag(task, TODAY_TAG)) task.tags = [...(task.tags || []), TODAY_TAG]
  } else {
    task.started_at = null
  }
  try {
    const updated = await updateTask(task.id, { status: next })
    task.status = updated.status
    task.started_at = updated.started_at
    task.elapsed_seconds = updated.elapsed_seconds
    task.tags = updated.tags
  } catch (err) {
    console.error(err)
    task.status = prev.status
    task.started_at = prev.started_at
    task.tags = prev.tags
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

// Reset the focus timer: zero elapsed time and return the task to idle (todo).
async function resetTimer(task) {
  const prev = { status: task.status, started_at: task.started_at, elapsed_seconds: task.elapsed_seconds }
  task.status = 'todo'
  task.started_at = null
  task.elapsed_seconds = 0
  try {
    const updated = await updateTask(task.id, { reset_elapsed: true })
    task.status = updated.status
    task.started_at = updated.started_at
    task.elapsed_seconds = updated.elapsed_seconds
  } catch (err) {
    console.error(err)
    task.status = prev.status
    task.started_at = prev.started_at
    task.elapsed_seconds = prev.elapsed_seconds
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

async function saveTimebox(task, minutes) {
  // 0, empty, or null all mean "no timebox" (cleared).
  const val = minutes === '' || minutes == null || Number(minutes) <= 0 ? null : Math.floor(Number(minutes))
  if (val === (task.timebox_minutes ?? null)) return
  try {
    const updated = await updateTask(task.id, { timebox_minutes: val })
    task.timebox_minutes = updated.timebox_minutes
  } catch (err) {
    console.error(err)
    connectionError.value = 'Could not update task — backend unreachable.'
    appStatus.value = 'error'
  }
}

// Step the timebox up/down by 5 minutes. Going to 0 or below clears it (null).
async function adjustTimebox(task, delta) {
  const current = task.timebox_minutes ?? 0
  const next = current + delta
  if (next <= 0) {
    await saveTimebox(task, null)
    return
  }
  await saveTimebox(task, next)
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
    had ? 'Removed from Today' : 'Added to Today',
    () => { task.tags = prevTags },
    async () => {
      try {
        const updated = await updateTask(task.id, { tags: newTags })
        task.tags = updated.tags
      } catch (err) {
        console.error(err)
        task.tags = prevTags
      }
    }
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
    recurring ? 'Made recurring' : 'Removed recurring',
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
    }
  )
}

// Delete a task. Deletes immediately (no confirmation) and shows an Undo toast
// for the toast window. Undo re-inserts the task at its previous position;
// otherwise the backend delete is committed.
function removeTask(task) {
  const index = tasks.value.findIndex(t => t.id === task.id)
  if (index !== -1) tasks.value.splice(index, 1)
  startUndo(
    task.id, 'delete',
    'Task deleted',
    () => {
      if (index !== -1) tasks.value.splice(index, 0, task)
    },
    async () => {
      try {
        await deleteTask(task.id)
      } catch (err) {
        console.error(err)
        if (index !== -1) tasks.value.splice(index, 0, task)
      }
    }
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

function onDocKeydown(event) {
  if (event.key === 'Escape') closeMenu()
}

onMounted(async () => {
  startWatchdog()
  await connect()
  await loadSettings()
  loadMics()
  startClock()
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onDocKeydown)
})

onUnmounted(() => {
  stopWatchdog()
  stopClock()
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onDocKeydown)
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
          <AppIcon name="diamond" class="w-3.5 h-3.5 inline-block text-sky-400 -mt-0.5" /> DISPATCH
        </h1>
        <p class="text-[11px] text-zinc-500">ai-powered task hud</p>
      </div>
      <div v-if="appStatus !== 'ready'" class="flex items-center gap-2">
        <span
          v-if="appStatus === 'loading'"
          class="inline-flex items-center gap-1.5 text-[11px] text-amber-400/90"
        >
          <AppIcon name="spinner" class="w-3.5 h-3.5 animate-spin" />
          Loading…
        </span>
        <span
          v-else-if="appStatus === 'error'"
          class="inline-flex items-center gap-1.5 text-[11px] text-red-400/90"
          title="Click to retry connecting"
        >
          <AppIcon name="alert" class="w-3.5 h-3.5" />
          Offline
        </span>
      </div>
      <div class="flex items-center">
        <button
          @click="toggleTheme"
          class="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-800 flex items-center gap-1.5"
          title="Switch to light theme"
        >
          <AppIcon name="sun" class="w-3.5 h-3.5" />
        </button>
        <button
          v-if="isTauri"
          @click="hideHud"
          class="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded hover:bg-zinc-800 flex items-center gap-1.5 ml-2 pl-2 border-l border-zinc-700/50"
          title="Hide HUD (restore from the system tray)"
        >
          <AppIcon name="minus" class="w-4 h-4" />
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
        <AppIcon name="mic" class="w-3 h-3 inline-block -mt-0.5" /> Listening — tap the mic or press Enter when done
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
          <AppIcon name="mic" class="w-3.5 h-3.5" />
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
          <AppIcon name="sparkles" class="w-3.5 h-3.5" />
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
      <div class="flex items-center justify-between mb-2 text-[11px]">
        <div class="flex items-center gap-1">
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
        <div class="flex items-center gap-1.5" data-testid="paging">
          <span class="text-zinc-500">Page</span>
          <button
            data-testid="page-prev"
            @click="page = Math.max(1, page - 1)"
            :disabled="page <= 1"
            class="px-1.5 py-0.5 rounded border border-zinc-700/50 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
            :class="page > 1 ? 'text-zinc-300 hover:border-zinc-500' : 'text-zinc-600'"
          >‹</button>
          <span class="text-zinc-400 tabular-nums">{{ page }} / {{ totalPages }}</span>
          <button
            data-testid="page-next"
            @click="page = Math.min(totalPages, page + 1)"
            :disabled="page >= totalPages"
            class="px-1.5 py-0.5 rounded border border-zinc-700/50 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
            :class="page < totalPages ? 'text-zinc-300 hover:border-zinc-500' : 'text-zinc-600'"
          >›</button>
          <select
            data-testid="page-size"
            :value="pageSize"
            @change="setPageSize(Number($event.target.value))"
            class="bg-zinc-800 border border-zinc-700/50 rounded px-1 py-0.5 text-zinc-300 cursor-pointer outline-none"
          >
            <option v-for="n in PAGE_SIZE_OPTIONS" :key="n" :value="n">{{ n }}</option>
          </select>
        </div>
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
            :class="item.task.done
              ? 'bg-zinc-800/30'
              : item.task.status === 'active'
                ? 'bg-emerald-500/10 ring-1 ring-emerald-500/40'
                : 'hover:bg-zinc-800/50'"
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
                data-testid="task-focus"
                @click.stop="toggleFocus(item.task)"
                class="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer"
                :class="item.task.status === 'active'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                  : item.task.status === 'paused'
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                    : 'text-zinc-500 border-zinc-700/50 hover:text-emerald-300 hover:border-emerald-500/40'"
                :title="item.task.status === 'active' ? 'Pause task' : 'Start task'"
              >
                <AppIcon :name="item.task.status === 'active' ? 'pause' : 'play'" class="w-3 h-3" />
                <span v-if="item.task.status === 'active' || item.task.status === 'paused'">{{ formatDuration(effectiveElapsed(item.task)) }}</span>
              </button>
              <button
                data-testid="task-expand"
                @click.stop="toggleExpand(item.task)"
                class="text-zinc-500 hover:text-sky-300 transition-colors shrink-0 cursor-pointer px-0.5"
                :title="expandedId === item.task.id ? 'Collapse' : 'Expand'"
              ><AppIcon :name="expandedId === item.task.id ? 'chevron-down' : 'chevron-right'" class="w-3.5 h-3.5" /></button>
              <div class="relative shrink-0" @click.stop>
                <button
                  data-testid="task-menu"
                  @click.stop="toggleMenu(item.task.id)"
                  class="text-zinc-500 hover:text-zinc-200 transition-colors cursor-pointer px-0.5"
                  :title="'More actions'"
                  :aria-expanded="menuOpenId === item.task.id"
                  aria-haspopup="true"
                ><AppIcon name="more" class="w-3.5 h-3.5" /></button>
                <div
                  v-if="menuOpenId === item.task.id"
                  data-testid="task-menu-popup"
                  class="absolute right-0 top-full mt-1 z-20 w-40 rounded-md border border-zinc-700/60 bg-zinc-900 shadow-lg py-1"
                  role="menu"
                >
                  <button
                    data-testid="menu-today"
                    @click.stop="toggleToday(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-zinc-800 transition-colors cursor-pointer flex items-center gap-2"
                    :class="hasTag(item.task, TODAY_TAG) ? 'text-sky-300' : 'text-zinc-300'"
                  >{{ hasTag(item.task, TODAY_TAG) ? 'Remove from Today' : 'Add to Today' }}</button>
                  <button
                    data-testid="menu-recurring"
                    @click.stop="toggleRecurring(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-zinc-800 transition-colors cursor-pointer flex items-center gap-2"
                    :class="item.task.recurring ? 'text-violet-300' : 'text-zinc-300'"
                  >{{ item.task.recurring ? 'Remove recurring' : 'Make recurring' }}</button>
                  <button
                    v-if="item.task.status === 'active' || item.task.status === 'paused' || (item.task.elapsed_seconds || 0) > 0"
                    data-testid="menu-reset"
                    @click.stop="resetTimer(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-zinc-800 transition-colors cursor-pointer text-zinc-300"
                  >Reset timer</button>
                  <div class="my-1 h-px bg-zinc-700/50"></div>
                  <button
                    data-testid="menu-delete"
                    @click.stop="removeTask(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-red-500/10 transition-colors cursor-pointer text-red-400"
                  >Delete</button>
                </div>
              </div>
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
            <div class="flex items-center gap-2 mb-2 text-[10px] text-zinc-500">
              <label class="shrink-0">Timebox</label>
              <div class="flex items-center rounded-md border border-zinc-700/60 overflow-hidden" data-testid="task-timebox">
                <button
                  data-testid="timebox-minus"
                  @click.stop="adjustTimebox(item.task, -5)"
                  class="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
                  title="Decrease by 5 min"
                >−</button>
                <input
                  type="text"
                  inputmode="numeric"
                  :value="item.task.timebox_minutes ?? ''"
                  data-testid="task-timebox-input"
                  @change="saveTimebox(item.task, $event.target.value)"
                  @keydown.enter="$event.target.blur()"
                  placeholder="–"
                  class="w-12 px-1 py-0.5 text-center text-xs text-zinc-200 placeholder-zinc-600 tabular-nums bg-transparent focus:outline-none appearance-none"
                />
                <button
                  data-testid="timebox-plus"
                  @click.stop="adjustTimebox(item.task, 5)"
                  class="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
                  title="Increase by 5 min"
                >+</button>
              </div>
              <span class="shrink-0">min</span>
              <span v-if="item.task.status === 'active' || item.task.status === 'paused'" class="shrink-0 text-zinc-400">{{ formatDuration(effectiveElapsed(item.task)) }} elapsed</span>
            </div>
            <div
              v-if="item.task.timebox_minutes"
              data-testid="task-progress"
              class="mb-2 h-1.5 rounded-full bg-zinc-800 overflow-hidden"
            >
              <div
                class="h-full rounded-full transition-all"
                :class="effectiveElapsed(item.task) >= item.task.timebox_minutes * 60 ? 'bg-red-500' : 'bg-emerald-500'"
                :style="{ width: Math.min(100, (effectiveElapsed(item.task) / (item.task.timebox_minutes * 60)) * 100) + '%' }"
              ></div>
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
      <div key="sort-row" class="flex items-center justify-center gap-1 pt-3 pb-1 text-[11px]">
        <span class="text-zinc-500 mr-1">sort</span>
        <div class="relative flex rounded bg-zinc-800/60 p-0.5">
          <span
            class="absolute inset-y-0.5 left-0.5 w-[calc(50%-2px)] rounded bg-zinc-700 transition-transform duration-300 ease"
            :style="{ transform: `translateX(${sortPillPos * 100}%)` }"
          ></span>
          <button
            data-testid="sort-priority"
            @click="sortMode = 'priority'"
            class="relative z-10 px-2 py-0.5 rounded transition-colors"
            :class="sortMode === 'priority' ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
          >Priority</button>
          <button
            data-testid="sort-created"
            @click="sortMode = 'created'"
            class="relative z-10 px-2 py-0.5 rounded transition-colors"
            :class="sortMode === 'created' ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'"
          >Created</button>
        </div>
      </div>
      </TransitionGroup>
      <div v-if="appStatus==='ready' && tasks.length === 0" class="flex flex-col items-center justify-center py-12 text-zinc-600">
        <AppIcon name="diamond" class="w-8 h-8 mb-2 opacity-30" />
        <p class="text-sm">No tasks yet</p>
        <p class="text-xs text-zinc-700 mt-1">Type something above to get started</p>
      </div>
    </div>

    <footer class="flex-none flex items-center justify-between pt-3 mt-3 border-t border-zinc-700/50 text-[11px] text-zinc-600">
      <span>{{ tasks.length }} task{{ tasks.length !== 1 ? 's' : '' }}</span>
      <span class="text-zinc-700">Ctrl+Enter to submit</span>
    </footer>

    <!-- Global undo toast -->
    <div class="fixed bottom-4 left-0 right-0 z-50 flex justify-center pointer-events-none">
      <Transition name="toast">
        <div
          v-if="undo"
          data-testid="undo-toast"
          class="pointer-events-auto flex items-center gap-3 px-4 py-2.5 rounded-lg border border-zinc-700/60 bg-zinc-800/95 shadow-xl"
        >
          <span class="text-xs text-zinc-200">{{ undo.message }}</span>
          <button
            data-testid="undo-toast-btn"
            @click="undoNow"
            class="text-xs font-medium text-sky-300 hover:text-sky-200 transition-colors cursor-pointer"
          >Undo</button>
        </div>
      </Transition>
    </div>
  </div>

  <!-- Light theme -->
  <div
    v-else
    class="h-full w-full bg-white/95 text-zinc-800 p-5 flex flex-col overflow-hidden select-none"
  >
    <header class="flex-none flex items-center justify-between pb-3 mb-3 border-b border-zinc-200/80" data-tauri-drag-region>
      <div>
        <h1 class="text-base font-semibold tracking-wider text-zinc-800">
          <AppIcon name="diamond" class="w-3.5 h-3.5 inline-block text-sky-500 -mt-0.5" /> DISPATCH
        </h1>
        <p class="text-[11px] text-zinc-400">ai-powered task hud</p>
      </div>
      <div v-if="appStatus !== 'ready'" class="flex items-center gap-2">
        <span
          v-if="appStatus === 'loading'"
          class="inline-flex items-center gap-1.5 text-[11px] text-amber-500/90"
        >
          <AppIcon name="spinner" class="w-3.5 h-3.5 animate-spin" />
          Loading…
        </span>
        <span
          v-else-if="appStatus === 'error'"
          class="inline-flex items-center gap-1.5 text-[11px] text-red-500/90"
          title="Click to retry connecting"
        >
          <AppIcon name="alert" class="w-3.5 h-3.5" />
          Offline
        </span>
      </div>
      <div class="flex items-center">
        <button
          @click="toggleTheme"
          class="text-[11px] text-zinc-400 hover:text-zinc-600 transition-colors px-2 py-1 rounded hover:bg-zinc-100 flex items-center gap-1.5"
          title="Switch to dark theme"
        >
          <AppIcon name="moon" class="w-3.5 h-3.5" />
        </button>
        <button
          v-if="isTauri"
          @click="hideHud"
          class="text-[11px] text-zinc-400 hover:text-zinc-600 transition-colors px-2 py-1 rounded hover:bg-zinc-100 flex items-center gap-1.5 ml-2 pl-2 border-l border-zinc-200"
          title="Hide HUD (restore from the system tray)"
        >
          <AppIcon name="minus" class="w-4 h-4" />
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
        <AppIcon name="mic" class="w-3 h-3 inline-block -mt-0.5" /> Listening — tap the mic or press Enter when done
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
          <AppIcon name="mic" class="w-3.5 h-3.5" />
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
          <AppIcon name="sparkles" class="w-3.5 h-3.5" />
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
      <div class="flex items-center justify-between mb-2 text-[11px]">
        <div class="flex items-center gap-1">
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
        <div class="flex items-center gap-1.5" data-testid="paging">
          <span class="text-zinc-400">Page</span>
          <button
            data-testid="page-prev"
            @click="page = Math.max(1, page - 1)"
            :disabled="page <= 1"
            class="px-1.5 py-0.5 rounded border border-zinc-200 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
            :class="page > 1 ? 'text-zinc-600 hover:border-zinc-400' : 'text-zinc-300'"
          >‹</button>
          <span class="text-zinc-500 tabular-nums">{{ page }} / {{ totalPages }}</span>
          <button
            data-testid="page-next"
            @click="page = Math.min(totalPages, page + 1)"
            :disabled="page >= totalPages"
            class="px-1.5 py-0.5 rounded border border-zinc-200 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default"
            :class="page < totalPages ? 'text-zinc-600 hover:border-zinc-400' : 'text-zinc-300'"
          >›</button>
          <select
            data-testid="page-size"
            :value="pageSize"
            @change="setPageSize(Number($event.target.value))"
            class="bg-white border border-zinc-200 rounded px-1 py-0.5 text-zinc-600 cursor-pointer outline-none"
          >
            <option v-for="n in PAGE_SIZE_OPTIONS" :key="n" :value="n">{{ n }}</option>
          </select>
        </div>
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
            :class="item.task.done
              ? 'bg-zinc-50/50'
              : item.task.status === 'active'
                ? 'bg-emerald-500/10 ring-1 ring-emerald-500/40'
                : 'hover:bg-zinc-50'"
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
                data-testid="task-focus"
                @click.stop="toggleFocus(item.task)"
                class="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border transition-colors shrink-0 cursor-pointer"
                :class="item.task.status === 'active'
                  ? 'bg-emerald-500/15 text-emerald-600 border-emerald-500/40'
                  : item.task.status === 'paused'
                    ? 'bg-amber-500/15 text-amber-600 border-amber-500/40'
                    : 'text-zinc-400 border-zinc-200 hover:text-emerald-600 hover:border-emerald-400/50'"
                :title="item.task.status === 'active' ? 'Pause task' : 'Start task'"
              >
                <AppIcon :name="item.task.status === 'active' ? 'pause' : 'play'" class="w-3 h-3" />
                <span v-if="item.task.status === 'active' || item.task.status === 'paused'">{{ formatDuration(effectiveElapsed(item.task)) }}</span>
              </button>
              <button
                data-testid="task-expand"
                @click.stop="toggleExpand(item.task)"
                class="text-zinc-400 hover:text-sky-600 transition-colors shrink-0 cursor-pointer px-0.5"
                :title="expandedId === item.task.id ? 'Collapse' : 'Expand'"
              ><AppIcon :name="expandedId === item.task.id ? 'chevron-down' : 'chevron-right'" class="w-3.5 h-3.5" /></button>
              <div class="relative shrink-0" @click.stop>
                <button
                  data-testid="task-menu"
                  @click.stop="toggleMenu(item.task.id)"
                  class="text-zinc-400 hover:text-zinc-700 transition-colors cursor-pointer px-0.5"
                  :title="'More actions'"
                  :aria-expanded="menuOpenId === item.task.id"
                  aria-haspopup="true"
                ><AppIcon name="more" class="w-3.5 h-3.5" /></button>
                <div
                  v-if="menuOpenId === item.task.id"
                  data-testid="task-menu-popup"
                  class="absolute right-0 top-full mt-1 z-20 w-40 rounded-md border border-zinc-200 bg-white shadow-lg py-1"
                  role="menu"
                >
                  <button
                    data-testid="menu-today"
                    @click.stop="toggleToday(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-zinc-100 transition-colors cursor-pointer flex items-center gap-2"
                    :class="hasTag(item.task, TODAY_TAG) ? 'text-sky-600' : 'text-zinc-700'"
                  >{{ hasTag(item.task, TODAY_TAG) ? 'Remove from Today' : 'Add to Today' }}</button>
                  <button
                    data-testid="menu-recurring"
                    @click.stop="toggleRecurring(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-zinc-100 transition-colors cursor-pointer flex items-center gap-2"
                    :class="item.task.recurring ? 'text-violet-600' : 'text-zinc-700'"
                  >{{ item.task.recurring ? 'Remove recurring' : 'Make recurring' }}</button>
                  <button
                    v-if="item.task.status === 'active' || item.task.status === 'paused' || (item.task.elapsed_seconds || 0) > 0"
                    data-testid="menu-reset"
                    @click.stop="resetTimer(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-zinc-100 transition-colors cursor-pointer text-zinc-700"
                  >Reset timer</button>
                  <div class="my-1 h-px bg-zinc-200"></div>
                  <button
                    data-testid="menu-delete"
                    @click.stop="removeTask(item.task); closeMenu()"
                    role="menuitem"
                    class="w-full text-left text-[11px] px-3 py-1.5 hover:bg-red-50 transition-colors cursor-pointer text-red-500"
                  >Delete</button>
                </div>
              </div>
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
            <div class="flex items-center gap-2 mb-2 text-[10px] text-zinc-500">
              <label class="shrink-0">Timebox</label>
              <div class="flex items-center rounded-md border border-zinc-200 overflow-hidden" data-testid="task-timebox">
                <button
                  data-testid="timebox-minus"
                  @click.stop="adjustTimebox(item.task, -5)"
                  class="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
                  title="Decrease by 5 min"
                >−</button>
                <input
                  type="text"
                  inputmode="numeric"
                  :value="item.task.timebox_minutes ?? ''"
                  data-testid="task-timebox-input"
                  @change="saveTimebox(item.task, $event.target.value)"
                  @keydown.enter="$event.target.blur()"
                  placeholder="–"
                  class="w-12 px-1 py-0.5 text-center text-xs text-zinc-700 placeholder-zinc-400 tabular-nums bg-transparent focus:outline-none appearance-none"
                />
                <button
                  data-testid="timebox-plus"
                  @click.stop="adjustTimebox(item.task, 5)"
                  class="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
                  title="Increase by 5 min"
                >+</button>
              </div>
              <span class="shrink-0">min</span>
              <span v-if="item.task.status === 'active' || item.task.status === 'paused'" class="shrink-0 text-zinc-400">{{ formatDuration(effectiveElapsed(item.task)) }} elapsed</span>
            </div>
            <div
              v-if="item.task.timebox_minutes"
              data-testid="task-progress"
              class="mb-2 h-1.5 rounded-full bg-zinc-200 overflow-hidden"
            >
              <div
                class="h-full rounded-full transition-all"
                :class="effectiveElapsed(item.task) >= item.task.timebox_minutes * 60 ? 'bg-red-500' : 'bg-emerald-500'"
                :style="{ width: Math.min(100, (effectiveElapsed(item.task) / (item.task.timebox_minutes * 60)) * 100) + '%' }"
              ></div>
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
      <div key="sort-row" class="flex items-center justify-center gap-1 pt-3 pb-1 text-[11px]">
        <span class="text-zinc-400 mr-1">sort</span>
        <div class="relative flex rounded bg-zinc-200/70 p-0.5">
          <span
            class="absolute inset-y-0.5 left-0.5 w-[calc(50%-2px)] rounded bg-white shadow-sm transition-transform duration-300 ease"
            :style="{ transform: `translateX(${sortPillPos * 100}%)` }"
          ></span>
          <button
            data-testid="sort-priority"
            @click="sortMode = 'priority'"
            class="relative z-10 px-2 py-0.5 rounded transition-colors"
            :class="sortMode === 'priority' ? 'text-zinc-700' : 'text-zinc-400 hover:text-zinc-600'"
          >Priority</button>
          <button
            data-testid="sort-created"
            @click="sortMode = 'created'"
            class="relative z-10 px-2 py-0.5 rounded transition-colors"
            :class="sortMode === 'created' ? 'text-zinc-700' : 'text-zinc-400 hover:text-zinc-600'"
          >Created</button>
        </div>
      </div>
      </TransitionGroup>
      <div v-if="appStatus==='ready' && tasks.length === 0" class="flex flex-col items-center justify-center py-12 text-zinc-300">
        <AppIcon name="diamond" class="w-8 h-8 mb-2 opacity-40" />
        <p class="text-sm text-zinc-400">No tasks yet</p>
        <p class="text-xs text-zinc-300 mt-1">Type something above to get started</p>
      </div>
    </div>

    <footer class="flex-none flex items-center justify-between pt-3 mt-3 border-t border-zinc-200/80 text-[11px] text-zinc-400">
      <span>{{ tasks.length }} task{{ tasks.length !== 1 ? 's' : '' }}</span>
      <span class="text-zinc-300">Ctrl+Enter to submit</span>
    </footer>

    <!-- Global undo toast -->
    <div class="fixed bottom-4 left-0 right-0 z-50 flex justify-center pointer-events-none">
      <Transition name="toast">
        <div
          v-if="undo"
          data-testid="undo-toast"
          class="pointer-events-auto flex items-center gap-3 px-4 py-2.5 rounded-lg border border-zinc-300 bg-white/95 shadow-xl"
        >
          <span class="text-xs text-zinc-700">{{ undo.message }}</span>
          <button
            data-testid="undo-toast-btn"
            @click="undoNow"
            class="text-xs font-medium text-sky-600 hover:text-sky-700 transition-colors cursor-pointer"
          >Undo</button>
        </div>
      </Transition>
    </div>
  </div>
</template>