import asyncio
import json
import websockets
from config import settings


DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


async def stream_transcribe():
    """Connect to Deepgram streaming API via raw WebSocket."""
    transcript_queue = asyncio.Queue()
    audio_queue = asyncio.Queue()

    lang = settings.deepgram_language
    params = {
        "model": "nova-3",
        "smart_format": "true",
        "interim_results": "true",
        "endpointing": "400",
        "utterance_end_ms": "1500",
        "encoding": "opus",
    }
    if lang:
        params["language"] = lang
    else:
        params["multilingual"] = "true"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{DEEPGRAM_WS_URL}?{query}"

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
    }

    # Flag to signal when to stop
    stop_event = asyncio.Event()

    async def run():
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
                last_final_time = 0
                async for raw in ws:
                    msg = json.loads(raw)
                    now = asyncio.get_event_loop().time()

                    if msg.get("type") == "UtteranceEnd":
                        if current_utterance.strip():
                            full_transcript += (" " if full_transcript else "") + current_utterance.strip()
                            await transcript_queue.put({"text": full_transcript, "done": True})
                            current_utterance = ""
                            last_interim = ""
                        # Deepgram detected silence — tell frontend to stop
                        await transcript_queue.put({"stop": True})
                        return

                    # If we haven't gotten a final result in 3 seconds, stop
                    if last_final_time and (now - last_final_time) > 3.0 and full_transcript:
                        await transcript_queue.put({"stop": True})
                        return

                    if msg.get("type") != "Results":
                        continue
                    sentence = msg.get("channel", {}).get("alternatives", [{}])[0].get("transcript", "")
                    if not sentence:
                        continue
                    is_final = msg.get("is_final", False)
                    if is_final:
                        print(f"[deepgram] final={is_final} text='{sentence[:100]}'")
                        last_final_time = now
                        if sentence not in full_transcript:
                            full_transcript += (" " if full_transcript else "") + sentence
                        await transcript_queue.put({"text": full_transcript, "done": True})
                        current_utterance = ""
                        last_interim = ""
                    else:
                        print(f"[deepgram] final={is_final} text='{sentence[:100]}'")
                        # Interim — show the full transcript + current thought
                        display = full_transcript + (" " if full_transcript else "") + sentence if sentence else full_transcript
                        if display != last_interim:
                            await transcript_queue.put({"text": display, "done": False})
                            last_interim = display

            sender_task = asyncio.create_task(sender())
            receiver_task = asyncio.create_task(receiver())

            print("[stream] Deepgram streaming connected")
            await stop_event.wait()
            print("[stream] stopping Deepgram connection")
            sender_task.cancel()
            receiver_task.cancel()

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


