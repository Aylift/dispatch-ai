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
                accumulated = ""
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "Results":
                        sentence = msg["channel"]["alternatives"][0]["transcript"]
                        if sentence:
                            is_final = msg.get("is_final", False)
                            if is_final:
                                accumulated = sentence
                            await transcript_queue.put({"text": sentence, "done": False})
                    elif msg.get("type") == "UtteranceEnd":
                        if accumulated.strip():
                            await transcript_queue.put({"text": accumulated.strip(), "done": True})
                        accumulated = ""

            sender_task = asyncio.create_task(sender())
            receiver_task = asyncio.create_task(receiver())

            await stop_event.wait()
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

