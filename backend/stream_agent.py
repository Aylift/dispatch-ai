import asyncio
import json
import time
import websockets
from config import settings


DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


def _ts() -> str:
    """Millisecond-precision timestamp for log lines."""
    return time.strftime("%H:%M:%S", time.localtime()) + f".{int(time.time() * 1000) % 1000:03d}"


def accumulate_transcript(state, msg):
    """Pure accumulator for Deepgram streaming results.

    Deepgram interims are CUMULATIVE within an utterance, so we never append the
    whole interim sentence to the committed transcript. We track the last
    committed prefix and the current utterance's latest interim, and only commit
    the DELTA (new words) when a final arrives. This prevents duplication and
    overwrite bugs.

    `state` is a dict with keys: committed (str), utterance (str),
    last_emitted (str). Returns (new_state, emit_or_None) where emit_or_None is
    a dict {"text": str, "done": bool} to send to the frontend, or None.
    """
    committed = state["committed"]
    utterance = state["utterance"]
    last_emitted = state["last_emitted"]

    # UtteranceEnd = Deepgram detected a pause. The final result already
    # committed the utterance; just reset per-utterance state.
    if msg.get("type") == "UtteranceEnd":
        return {**state, "utterance": ""}, None

    if msg.get("type") != "Results":
        return state, None

    sentence = msg.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
    if not sentence:
        return state, None

    is_final = msg.get("is_final", False)
    if is_final:
        # Commit only the words not already in the committed transcript.
        if not committed.endswith(sentence):
            committed = (committed + " " + sentence).strip()
        utterance = ""
        emit = {"text": committed, "done": True} if committed != last_emitted else None
        return {"committed": committed, "utterance": utterance, "last_emitted": committed}, emit

    # Interim - show committed prefix + current thought.
    utterance = sentence
    display = (committed + " " + utterance).strip()
    emit = {"text": display, "done": False} if display != last_emitted else None
    return {"committed": committed, "utterance": utterance, "last_emitted": display}, emit


def build_deepgram_url() -> str:
    """Build the Deepgram streaming listen URL from current settings."""
    lang = settings.deepgram_language
    params = {
        "model": "nova-3",
        "smart_format": "true",
        "interim_results": "true",
        # Short endpointing so a brief pause finalizes the current utterance
        # quickly (lower latency). The stream stays open; stopping is the
        # user's decision (frontend).
        # NOTE: utterance_end_ms is NOT used here - Deepgram rejects that
        # param (HTTP 400) for the billing/model combination in use.
        "endpointing": "300",
        "encoding": "linear16",
        "sample_rate": "48000",
    }
    if lang:
        params["language"] = lang
    else:
        params["multilingual"] = "true"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{DEEPGRAM_WS_URL}?{query}"


async def stream_transcribe(idle_timeout: float = 10.0):
    """Connect to Deepgram streaming API via raw WebSocket.

    Auto-stops (and tells the frontend to release the mic) after `idle_timeout`
    seconds of no detected speech, so we don't waste resources on a silent mic.
    """
    transcript_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    url = build_deepgram_url()

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
    }

    # Flag to signal when to stop
    stop_event = asyncio.Event()

    async def run():
        # Mutable holders shared by receiver + close() closures
        last_activity = [0.0]
        committed = [""]      # finalized text, never rewritten
        last_emitted = [""]   # last string sent to the frontend

        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                # Task that sends audio chunks to Deepgram
                async def sender():
                    sent_bytes = 0
                    while True:
                        chunk = await audio_queue.get()
                        if chunk is None:
                            break
                        await ws.send(chunk)
                        sent_bytes += len(chunk)
                        if sent_bytes % (48000 * 2 * 10) < len(chunk):
                            print(f"[{_ts()}] [stream] sent {len(chunk)}B audio (total {sent_bytes}B)")

                # Task that receives messages from Deepgram and feeds them
                # through the pure accumulator (see accumulate_transcript).
                async def receiver():
                    state = {
                        "committed": committed[0],
                        "utterance": "",
                        "last_emitted": last_emitted[0],
                    }
                    async for raw in ws:
                        msg = json.loads(raw)
                        now = asyncio.get_event_loop().time()
                        mtype = msg.get("type")
                        sentence = msg.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                        is_final = msg.get("is_final", False)
                        # Any speech (not just finals) counts as activity
                        if mtype == "Results" and sentence:
                            last_activity[0] = now
                        if mtype == "Results":
                            print(f"[{_ts()}] [dg] Results final={is_final} len={len(sentence)} text={sentence!r}")
                        elif mtype:
                            print(f"[{_ts()}] [dg] {mtype}")
                        state, emit = accumulate_transcript(state, msg)
                        if emit:
                            print(f"[{_ts()}] [emit] done={emit.get('done')} text={emit.get('text')!r}")
                            await transcript_queue.put(emit)
                    committed[0] = state["committed"]
                    last_emitted[0] = state["last_emitted"]

                sender_task = asyncio.create_task(sender())
                receiver_task = asyncio.create_task(receiver())

                print(f"[{_ts()}] [stream] Deepgram streaming connected")
                # Wait for either an explicit stop or an idle timeout.
                while not stop_event.is_set():
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=idle_timeout)
                    except asyncio.TimeoutError:
                        if last_activity[0] and (asyncio.get_event_loop().time() - last_activity[0]) >= idle_timeout:
                            print(f"[{_ts()}] [stream] idle {idle_timeout}s - auto-stopping")
                            await transcript_queue.put({"idle": True})
                            break
                print(f"[{_ts()}] [stream] stopping Deepgram connection")
                # Flush the final committed transcript so nothing is lost when
                # the user stops (the WS is about to close).
                if committed[0] and committed[0] != last_emitted[0]:
                    print(f"[{_ts()}] [flush] committed={committed[0]!r}")
                    await transcript_queue.put({"text": committed[0], "done": True})
                else:
                    print(f"[{_ts()}] [flush] nothing to flush (committed={committed[0]!r} last_emitted={last_emitted[0]!r})")
                sender_task.cancel()
                receiver_task.cancel()
        except asyncio.CancelledError:
            # Client gave up / closed - not an error
            raise
        except Exception as exc:
            # Deepgram refused the connection or dropped mid-stream. Surface a
            # clear, friendly error to the frontend instead of crashing.
            print(f"[stream] Deepgram connection failed: {exc}")
            try:
                await transcript_queue.put({"error": str(exc)})
            except Exception:
                pass

    dg_task = asyncio.create_task(run())

    async def transcript_listener():
        while True:
            msg = await transcript_queue.get()
            yield msg

    async def send_audio(chunk: bytes):
        await audio_queue.put(chunk)

    async def close():
        stop_event.set()
        await audio_queue.put(None)
        await dg_task

    return send_audio, transcript_listener(), close
