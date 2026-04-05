# brain/ — LLM integration layer.
# Uses Ollama running locally with model auto-selection.

from .ollama_client import send_to_ollama

__all__ = ["send_to_ollama"]
