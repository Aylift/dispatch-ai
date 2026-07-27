from openai import OpenAI
import httpx
from config import settings

deepseek = OpenAI(
    api_key=settings.deepseek_api_key,
    base_url="https://api.deepseek.com",
)

lang = settings.deepgram_language
if lang:
    DEEPGRAM_URL = f"https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&language={lang}"
else:
    DEEPGRAM_URL = "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&multilingual=true"


def transcribe_audio(audio_data: bytes, filename: str = "recording.webm") -> str:
    """Transcribe audio using Deepgram API."""
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "audio/webm",
    }
    with httpx.Client() as client:
        response = client.post(DEEPGRAM_URL, headers=headers, content=audio_data)
        response.raise_for_status()
        data = response.json()
        return data["results"]["channels"][0]["alternatives"][0]["transcript"]
