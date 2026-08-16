const WS_URL = 'ws://localhost:8000/ws/transcribe'
const SAMPLE_RATE = 48000

const ts = () => new Date().toISOString().slice(11, 23)

export function useVoice({ onInterim, onStop, onError }) {
  let audioContext = null
  let sourceNode = null
  let processorNode = null
  let stream = null
  let ws = null
  let listening = false

  // Convert a Float32 PCM buffer ([-1, 1]) to 16-bit little-endian PCM bytes.
  function toPcm16(buffer) {
    const out = new Int16Array(buffer.length)
    for (let i = 0; i < buffer.length; i++) {
      const s = Math.max(-1, Math.min(1, buffer[i]))
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
    }
    return new Uint8Array(out.buffer)
  }

  async function start(deviceId) {
    if (listening) return
    listening = true
    console.log(`[${ts()}] [voice] start deviceId=${deviceId}`)

    ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'

    ws.onmessage = (event) => {
      let msg
      try { msg = JSON.parse(event.data) } catch { return }
      console.log(`[${ts()}] [voice] <- ${JSON.stringify(msg)}`)
      // Backend couldn't reach the transcription provider - surface it.
      if (msg.error) {
        stop()
        if (onError) onError(msg.error)
        return
      }
      // Backend auto-stopped after idle timeout - release the mic.
      if (msg.idle) {
        stop()
        if (onStop) onStop()
        return
      }
      if (msg.text) onInterim(msg.text, !!msg.done)
    }

    ws.onopen = async () => {
      console.log(`[${ts()}] [voice] ws open`)
      try {
        stream = await navigator.mediaDevices.getUserMedia(
          deviceId ? { audio: { deviceId: { exact: deviceId } } } : { audio: true }
        )
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: SAMPLE_RATE,
        })
        sourceNode = audioContext.createMediaStreamSource(stream)
        processorNode = audioContext.createScriptProcessor(4096, 1, 1)
        processorNode.onaudioprocess = (e) => {
          const input = e.inputBuffer.getChannelData(0)
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(toPcm16(input))
          }
        }
        sourceNode.connect(processorNode)
        processorNode.connect(audioContext.destination)
        await audioContext.resume()
        console.log(`[${ts()}] [voice] mic + audio graph ready`)
      } catch (err) {
        console.error(`[${ts()}] [voice] Mic start failed:`, err)
        listening = false
        if (onStop) onStop()
      }
    }

    ws.onclose = () => {
      console.log(`[${ts()}] [voice] ws closed`)
      stop()
    }
  }

  function stop() {
    if (!listening) return
    listening = false
    console.log(`[${ts()}] [voice] stop`)
    if (processorNode) {
      processorNode.disconnect()
      processorNode = null
    }
    if (sourceNode) {
      sourceNode.disconnect()
      sourceNode = null
    }
    if (stream) {
      stream.getTracks().forEach(t => t.stop())
      stream = null
    }
    if (audioContext) {
      audioContext.close()
      audioContext = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
  }

  return { start, stop, isListening: () => listening }
}
