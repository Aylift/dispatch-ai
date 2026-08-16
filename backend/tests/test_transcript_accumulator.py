"""Unit tests for the Deepgram transcript accumulator.

These exercise the pure accumulate_transcript() function with mocked Deepgram
message sequences to prove there is no duplication or overwrite across
interim/final/UtteranceEnd transitions.
"""

from stream_agent import accumulate_transcript


def _results(transcript, is_final=False):
    return {
        "type": "Results",
        "is_final": is_final,
        "channel": {"alternatives": [{"transcript": transcript}]},
    }


def _utterance_end():
    return {"type": "UtteranceEnd"}


def _state():
    return {"committed": "", "utterance": "", "last_emitted": ""}


def test_interim_then_final_commits_delta_once():
    state = _state()
    # Interim: cumulative "buy milk"
    state, emit = accumulate_transcript(state, _results("buy milk"))
    assert emit == {"text": "buy milk", "done": False}
    # Final: cumulative "buy milk and eggs" -> commit only the delta
    state, emit = accumulate_transcript(state, _results("buy milk and eggs", is_final=True))
    assert emit == {"text": "buy milk and eggs", "done": True}
    assert state["committed"] == "buy milk and eggs"
    # A repeated final must not duplicate
    state, emit = accumulate_transcript(state, _results("buy milk and eggs", is_final=True))
    assert emit is None
    assert state["committed"] == "buy milk and eggs"


def test_multiple_utterances_accumulate_without_duplication():
    state = _state()
    state, _ = accumulate_transcript(state, _results("buy milk", is_final=True))
    assert state["committed"] == "buy milk"
    state, _ = accumulate_transcript(state, _utterance_end())
    # Second utterance
    state, emit = accumulate_transcript(state, _results("call bob", is_final=True))
    assert emit == {"text": "buy milk call bob", "done": True}
    assert state["committed"] == "buy milk call bob"


def test_interim_does_not_commit():
    state = _state()
    state, emit = accumulate_transcript(state, _results("hello world"))
    assert emit == {"text": "hello world", "done": False}
    assert state["committed"] == ""
    # Refined interim replaces the display, still not committed
    state, emit = accumulate_transcript(state, _results("hello world today"))
    assert emit == {"text": "hello world today", "done": False}
    assert state["committed"] == ""


def test_empty_and_non_results_are_ignored():
    state = _state()
    state, emit = accumulate_transcript(state, {"type": "Metadata"})
    assert emit is None
    state, emit = accumulate_transcript(state, _results(""))
    assert emit is None
    assert state["committed"] == ""
