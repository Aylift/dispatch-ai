from openai import OpenAI
import httpx
import json
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


# Parse prompt: turn a natural-language dump into a structured todo list.
# Priorities: 1 = Critical, 2 = High, 3 = Medium (default), 4 = Low, 5 = Optional.
PARSE_SYSTEM_PROMPT = """You are Dispatch, a personal task assistant. Convert the user's natural-language "brain dump" into a concise to-do list.

Rules:
- Produce a JSON array of tasks. Each item: {"text": string, "priority": int, "description": string}
- Split multiple ideas/clauses into separate tasks. One idea = one task.
- "text" must be a short, actionable title (imperative, no fluff, no dates). Keep it under 10 words.
- "description" holds the supporting detail/context the user gave (reasons, steps, links, specifics). If there is no meaningful detail, use an empty string. Do not repeat the title.
- "priority" uses 1 (Critical), 2 (High), 3 (Medium), 4 (Low), 5 (Optional).
- Default any task with no explicit urgency to 3 (Medium).
- Infer urgency only from explicit signals (e.g. "asap", "urgent", "today", "important" => higher; "someday", "if i have time", "low priority" => lower).
- Output ONLY the JSON array, nothing else, no markdown."""


def parse_tasks(text: str) -> list[dict]:
    """Parse a natural-language dump into a list of {text, priority, description} tasks."""
    if not settings.deepseek_api_key:
        # No key configured: fall back to a single Medium task so dev still works
        return [{"text": text.strip(), "priority": 3, "description": ""}]

    try:
        completion = deepseek.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content or "[]"
        payload = json.loads(raw)
        items = payload if isinstance(payload, list) else payload.get("tasks", [])
    except Exception as exc:
        print(f"[agent] parse_tasks error: {exc}")
        return [{"text": text.strip(), "priority": 3, "description": ""}]

    tasks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        task_text = str(item.get("text", "")).strip()
        if not task_text:
            continue
        # Coerce priority to 1..5, defaulting to 3
        try:
            priority = int(item.get("priority", 3))
        except (TypeError, ValueError):
            priority = 3
        description = str(item.get("description", "") or "").strip()
        tasks.append({
            "text": task_text,
            "priority": max(1, min(5, priority)),
            "description": description,
        })

    if not tasks:
        tasks = [{"text": text.strip(), "priority": 3, "description": ""}]
    return tasks
