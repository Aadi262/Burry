# pipeline/ — extracted modules from butler.py
# Reduces the God Object by moving cohesive function clusters here.
# butler.py imports from these modules and delegates; signatures unchanged.
from pipeline.recorder import record as record_turn
from pipeline.speech import speak_or_print, speak_stream_chunk

__all__ = ["record_turn", "speak_or_print", "speak_stream_chunk"]
