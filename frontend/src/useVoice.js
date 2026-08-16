const WS_URL = 'ws://localhost:8000/ws/transcribe'

export function useVoice({ onInterim, onStop, onError }) {
  let mediaRecorder = null
  let ws = null
  let listening = false

  async function start(deviceId) {
    if (listening) return
    listening = true

    ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'

    ws.onmessage = (event) => {
      let msg
      try { msg = JSON.parse(event.data) } catch { return }
      // Backend couldn't reach the transcription provider - surface it.
      if (msg.error) {
        stop()
        if (onError) onError(msg.error)
        return
      }
      if (msg.text) onInterim(msg.text, !!msg.done)
    }

    ws.onopen = async () => {
      try {
        const constraints = deviceId
          ? { audio: { deviceId: { exact: deviceId } } }
          : { audio: true }
        const stream = await navigator.mediaDevices.getUserMedia(constraints)
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
    if (!listening) return
    listening = false
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
