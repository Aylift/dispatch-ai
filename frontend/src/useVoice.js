const WS_URL = 'ws://127.0.0.1:8000/ws/transcribe'

export function useVoice({ onPartial, onFinal }) {
  let mediaRecorder = null
  let ws = null
  let isListening = false

  async function start() {
    if (isListening) return
    isListening = true

    ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.done) {
        onFinal(msg.text)
        stop()
      } else if (!msg.done && msg.text) {
        onPartial(msg.text)
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
        mediaRecorder.start(250) // send chunks every 250ms
      } catch {
        isListening = false
      }
    }

    ws.onclose = () => {
      stop()
    }
  }

  function stop() {
    isListening = false
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stream?.getTracks().forEach(t => t.stop())
      mediaRecorder.stop()
    }
    if (ws) {
      ws.close()
      ws = null
    }
  }

  return { start, stop, isListening: () => isListening }
}

