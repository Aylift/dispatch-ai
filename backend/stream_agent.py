import asyncio
import json
import websockets
from config import settings


DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


def build_deepgram_url() -> str:
    """Build the Deepgram streaming listen URL from current settings."""
    lang = settings.deepgram_language
    params = {
        "model": "nova-3",
        "smart_format": "true",
        "interim_results": "true",
        # Generous silence window so short "thinking" pauses don't end the
        # session. endpointing finalizes the current utterance after 700ms of
        # silence without closing the stream, so the user can keep talking
        # after thinking. Stopping is the user's decision (frontend).
        # NOTE: utterance_end_ms is NOT used here - Deepgram rejects that
        # param (HTTP 400) for the billing/model combination in use.
        "endpointing": "700",
        "vad_events": "true",
        "encoding": "opus",
    }
    if lang:
        params["language"] = lang
    else:
        params["multilingual"] = "true"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{DEEPGRAM_WS_URL}?{query}"


async def stream_transcribe():
    """Connect to Deepgram streaming API via raw WebSocket."""
    transcript_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    url = build_deepgram_url()

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
    }

    # Flag to signal when to stop
    stop_event = asyncio.Event()

    async def run():
        # Mutable holder shared by receiver + watchdog closures
        last_activity = [0.0]

        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                # Task that sends audio chunks to Deepgram
                async def sender():
                    while True:
                        chunk = await audio_queue.get()
                        if chunk is None:
                            break
                        await ws.send(chunk)

                # Task that receives messages from Deepgram
                async def receiver():
                    full_transcript = ""
                    current_utterance = ""
                    last_interim = ""
                    async for raw in ws:
                        msg = json.loads(raw)
                        now = asyncio.get_event_loop().time()

                        # UtteranceEnd = Deepgram detected a pause. Informational:
                        # commit the finished thought but DO NOT tear down the
                        # connection, so the user can keep talking after thinking.
                        if msg.get("type") == "UtteranceEnd":
                            if current_utterance.strip():
                                full_transcript += (" " if full_transcript else "") + current_utterance.strip()
                                await transcript_queue.put({"text": full_transcript, "done": True})
                                current_utterance = ""
                                last_interim = ""
                            continue

                        if msg.get("type") != "Results":
                            continue

                        sentence = msg.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                        if not sentence:
                            continue
                        # Any speech (not just finals) counts as activity
                        last_activity[0] = now

                        is_final = msg.get("is_final", False)
                        if is_final:
                            print(f"[deepgram] final={is_final} text='{sentence[:100]}'")
                            if sentence not in full_transcript:
                                full_transcript += (" " if full_transcript else "") + sentence
                            await transcript_queue.put({"text": full_transcript, "done": True})
                            current_utterance = ""
                            last_interim = ""
                        else:
                            print(f"[deepgram] interim text='{sentence[:100]}'")
                            # Interim - show the full transcript + current thought
                            display = full_transcript + (" " if full_transcript else "") + sentence if sentence else full_transcript
                            if display != last_interim:
                                await transcript_queue.put({"text": display, "done": False})
                                last_interim = display

                # Safety net: stop only after a very long idle silence (no speech
                # at all for N seconds). Normal thinking pauses won't hit this;
                # the user mostly stops by pressing the mic again.
                async def idle_watchdog():
                    await asyncio.sleep(1)
                    while True:
                        await asyncio.sleep(0.5)
                        now = asyncio.get_event_loop().time()
                        if now - last_activity[0] > 12.0:
                            await transcript_queue.put({"idle_stop": True})
                            break

                sender_task = asyncio.create_task(sender())
                receiver_task = asyncio.create_task(receiver())
                watchdog_task = asyncio.create_task(idle_watchdog())

                print("[stream] Deepgram streaming connected")
                await stop_event.wait()
                print("[stream] stopping Deepgram connection")
                sender_task.cancel()
                receiver_task.cancel()
                watchdog_task.cancel()
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
