import pytest

from validation import validate_task_text


@pytest.mark.parametrize("text", [
    "buy milk",
    "kup mleko",
    "kup mleko na jutro",       # stopword + real word passes
    "call the dentist",          # stopword + real words passes
    "napisz raport do szefa",    # mixed PL
    "fix bug",
])
def test_accepts_actionable_text(text):
    assert validate_task_text(text) == text.strip()


@pytest.mark.parametrize("text", [
    "",
    "   ",
    "ab",                        # too short
    "na",                        # PL stopword only
    "do po za",                  # PL stopwords only
    "the on in",                 # EN stopwords only
    "i a the",                   # mixed stopwords only
    "się to jest",               # PL filler only (diacritics normalized)
    "!!!",                       # no word tokens
])
def test_rejects_filler_or_too_short(text):
    with pytest.raises(ValueError):
        validate_task_text(text)


def test_strips_whitespace():
    assert validate_task_text("  buy milk  ") == "buy milk"


def test_diacritics_normalized_for_stopword_check():
    # "się" normalizes to "sie" and must be recognized as a stopword.
    with pytest.raises(ValueError):
        validate_task_text("sie")
