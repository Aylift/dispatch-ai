"""Task text validation.

Rejects task titles that carry no actionable content: empty/too-short strings
and strings made up entirely of common stopwords (Polish + English). The user
writes mainly in Polish but also English, so both stopword sets are checked.

The rule is intentionally conservative: a title is only rejected when *every*
token is a stopword (or the title is shorter than MIN_LEN characters). A title
that mixes a stopword with a real word (e.g. "kup mleko na jutro") passes.
"""

import re
import unicodedata

MIN_LEN = 3

# Common Polish + English stopwords / filler words. Lowercased, no diacritics
# (we normalize input before comparing). Kept to genuinely content-free words so
# we never reject a real task.
STOPWORDS = {
    # Polish
    "na", "do", "od", "po", "za", "w", "we", "z", "ze", "i", "a", "o", "u",
    "nie", "tak", "to", "ta", "ten", "te", "ci", "sie", "się", "jest", "sa",
    "są", "by", "bym", "bys", "byś", "aby", "lub", "albo", "czy", "jak", "co",
    "gdy", "kiedy", "gdzie", "tu", "tam", "juz", "już", "jeszcze", "tylko",
    "oraz", "dla", "przez", "pod", "nad", "przy", "bez", "moj", "mój", "moja",
    "moje", "twoj", "twój", "jego", "jej", "ich", "nasz", "wasz", "siebie",
    "sobie", "moze", "może", "trzeba", "warto", "jakos", "jakoś", "no", "noo",
    # English
    "a", "an", "the", "on", "in", "at", "to", "of", "for", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "so",
    "if", "then", "than", "as", "by", "with", "from", "into", "onto", "up",
    "down", "out", "off", "over", "under", "this", "that", "these", "those",
    "it", "its", "my", "your", "his", "her", "our", "their", "me", "you",
    "him", "them", "we", "they", "i", "just", "only", "also", "very", "not",
    "no", "yes", "ok", "okay", "well", "here", "there", "when", "where", "how",
    "what", "which", "who", "whom", "some", "any", "all", "each", "every",
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _strip_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _tokens(text: str) -> list[str]:
    return [_strip_diacritics(t).lower() for t in _WORD_RE.findall(text)]


def validate_task_text(text: str) -> str:
    """Return the cleaned title, or raise ValueError with a user-facing message.

    Rejects:
      - empty / whitespace-only
      - shorter than MIN_LEN characters
      - every token is a stopword (no actionable content)
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Task text cannot be empty.")
    if len(cleaned) < MIN_LEN:
        raise ValueError(f"Task text is too short (min {MIN_LEN} characters).")

    tokens = _tokens(cleaned)
    # If there are no word tokens at all (e.g. only punctuation/emoji), reject.
    if not tokens:
        raise ValueError("Task text must contain at least one word.")
    if all(tok in STOPWORDS for tok in tokens):
        raise ValueError(
            "Task text looks like filler words only — add something actionable."
        )
    return cleaned
