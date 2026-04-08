"""pipeline/speech.py — TTS coordination extracted from butler.py.

Moves speak_or_print(), speak_stream_chunk(), and the streaming TTS helpers
out of the 3600-line God Object. butler.py imports these as thin aliases.
"""

from __future__ import annotations

import queue
import threading

from brain.ollama_client import stream_chat_with_ollama, stream_llm_tokens
from runtime import notify
from state import State, state
from voice import speak


def speak_or_print(text: str, test_mode: bool = False, *, speak_fn=None, notify_fn=None) -> None:
    """Speak text via TTS or print in test mode.

    B6: TTS fires in a background thread so the listening loop resumes
    immediately without waiting for speech to complete.
    """
    if not text:
        return
    speaker = speak_fn or speak
    notifier = notify_fn or notify
    state.transition(State.SPEAKING)
    if test_mode:
        print(f"[Butler would say]: {text}")
    else:
        def _speak_and_notify() -> None:
            speaker(text)
            notifier("Burry", text[:180], subtitle="Response")
        threading.Thread(target=_speak_and_notify, daemon=True, name="burry-tts").start()


def speak_stream_chunk(text: str, *, speak_fn=None) -> None:
    """Speak a single streaming sentence chunk."""
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return
    speaker = speak_fn or speak
    state.transition(State.SPEAKING)
    speaker(cleaned)


async def stream_response_with_tts(prompt: str, model: str) -> str:
    """Stream LLM response and speak each sentence as it arrives.
    STEAL 3: user hears first words within 1-2 seconds instead of waiting 45s.
    """
    return await stream_sentences_with_tts(stream_llm_tokens(prompt, model))


async def stream_sentences_with_tts(sentence_stream) -> str:
    """Consume streamed sentence chunks and serialize speech so chunks are not dropped."""
    spoken_sentences: list[str] = []
    speech_queue: queue.Queue[str | None] = queue.Queue()

    def _speaker() -> None:
        while True:
            sentence = speech_queue.get()
            try:
                if sentence is None:
                    return
                speak(sentence)
            finally:
                speech_queue.task_done()

    state.transition(State.SPEAKING)
    speaker_thread = threading.Thread(target=_speaker, daemon=True, name="burry-stream-tts")
    speaker_thread.start()
    try:
        async for sentence in sentence_stream:
            cleaned = " ".join(str(sentence or "").split()).strip()
            if not cleaned:
                continue
            spoken_sentences.append(cleaned)
            speech_queue.put(cleaned)
        return " ".join(spoken_sentences).strip()
    except Exception:
        return ""
    finally:
        speech_queue.put(None)
        speech_queue.join()
        speaker_thread.join(timeout=10)


async def stream_chat_response_with_tts(
    messages: list[dict],
    model: str,
    *,
    max_tokens: int = 140,
    temperature: float = 0.3,
) -> str:
    return await stream_sentences_with_tts(
        stream_chat_with_ollama(
            messages,
            model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )
