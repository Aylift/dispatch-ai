"""Integration tests that hit the real Deepgram API.

These validate the live Deepgram config (URL/params) doesn't regress to an
invalid combination (e.g. HTTP 400), which manifests as a runtime exception in
production. They are skipped when no DEEPGRAM_API_KEY is configured so normal
unit/CI runs don't depend on provider availability or cost.
"""

import asyncio
import json
import os
import pytest
import websockets

from config import settings
from stream_agent import build_deepgram_url, DEEPGRAM_WS_URL

needs_key = pytest.mark.skipif(
    not settings.deepgram_api_key,
    reason="No DEEPGRAM_API_KEY configured",
)


@needs_key
def test_deepgram_url_does_not_include_rejected_param():
    """Guard against reintroducing params Deepgram rejects with HTTP 400."""
    url = build_deepgram_url()
    assert "utterance_end_ms" not in url
    # The key required params are present
    assert "endpointing" in url
    assert "vad_events" in url


@needs_key
def test_deepgram_websocket_handshake_accepts_our_params():
    """The exact streaming URL must establish a WebSocket (no HTTP 400)."""
    url = build_deepgram_url()
    headers = {"Authorization": f"Token {settings.deepgram_api_key}"}

    async def probe():
        async with websockets.connect(url, additional_headers=headers, open_timeout=10) as ws:
            # Send a tiny payload so Deepgram has something to chew on
            await ws.send(b"\x00" * 100)
            # Read briefly; any valid result or metadata is fine. We mainly
            # assert the handshake succeeded (no InvalidStatus/400).
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                parsed = json.loads(raw)
                assert isinstance(parsed, dict)
                return parsed.get("type")
            except asyncio.TimeoutError:
                # No message is acceptable - we only care about the handshake.
                return None

    result = asyncio.run(probe())
    print(f"[dg-integration] handshake ok, first message type={result}")
    assert True
