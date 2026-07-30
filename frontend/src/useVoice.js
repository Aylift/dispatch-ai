const WS_URL = 'ws://localhost:8000/ws/transcribe'

export function useVoice({ onInterim, onStop }) {
  let mediaRecorder = null
  let ws = null
  let listening = false
  let doneTimeout = null

  async function start() {
    if (listening) return
    listening = true

    ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.stop) {
        console.log('[voice] received stop signal')
        stop()
        if (onStop) onStop()
        return
      }
      if (msg.done) {
        if (msg.text) onInterim(msg.text, true)
        if (doneTimeout) clearTimeout(doneTimeout)
        doneTimeout = setTimeout(() => {
          stop()
          if (onStop) onStop()
        }, 3000)
      } else if (msg.text) {
        onInterim(msg.text, false)
        if (doneTimeout) clearTimeout(doneTimeout)
        doneTimeout = setTimeout(() => {
          console.log('[voice] auto-stop timeout (interim)')
          stop()
          if (onStop) onStop()
        }, 5000)
      }
    }

    ws.onopen = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0 && ws?.readyState === WebSocket.OPEN) {
            ws.send(e.data)
          }
        }
        mediaRecorder.start(250)
      } catch {
        listening = false
        if (onStop) onStop()
      }
    }

    ws.onclose = () => stop()
  }

  function stop() {
    listening = false
    if (doneTimeout) { clearTimeout(doneTimeout); doneTimeout = null }
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stream?.getTracks().forEach(t => t.stop())
      mediaRecorder.stop()
    }
    if (ws) {
      ws.close()
      ws = null
    }
  }

  return { start, stop, isListening: () => listening }
}

