# voice/ — Text-to-speech output layer.
# Uses the best available local English voice and can switch to Piper later.

from .tts import describe_tts, shape_for_speech, speak
from .stt import (
    describe_stt,
    is_voice_follow_up_available,
    listen_continuous,
    listen_for_command,
    listen_for_follow_up,
)

__all__ = [
    "describe_tts",
    "describe_stt",
    "speak",
    "shape_for_speech",
    "is_voice_follow_up_available",
    "listen_for_command",
    "listen_continuous",
    "listen_for_follow_up",
]
