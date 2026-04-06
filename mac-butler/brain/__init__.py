# brain/ — LLM integration layer.
# Uses Ollama running locally with model auto-selection.

from butler_config import AGENT_MODELS, BUG_HUNTER_MODEL, BUTLER_MODELS, HEARTBEAT_MODEL

from .mood_engine import describe_mood_state, get_mood, get_mood_instruction
from .ollama_client import call_voice, send_to_ollama

MODELS = {
    "voice": BUTLER_MODELS.get("voice", ""),
    "planning": BUTLER_MODELS.get("planning", ""),
    "vision": BUTLER_MODELS.get("vision", BUTLER_MODELS.get("voice", "")),
    "reasoning": BUTLER_MODELS.get("review", ""),
    "agents": AGENT_MODELS.get("memory", ""),
    "heartbeat": HEARTBEAT_MODEL,
    "bugfinder": BUG_HUNTER_MODEL,
}

__all__ = [
    "MODELS",
    "call_voice",
    "describe_mood_state",
    "get_mood",
    "get_mood_instruction",
    "send_to_ollama",
]
