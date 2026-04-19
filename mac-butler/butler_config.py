#!/usr/bin/env python3
"""
butler_config.py — edit this to configure your setup.
"""

import os

# --- Paths ---
OBSIDIAN_VAULT_NAME = "Burry"
OBSIDIAN_VAULT_PATH = ""
DEVELOPER_PATH = "~/Developer"
BURRY_PATH = "~/Burry"

# --- VPS ---
VPS_HOSTS = [
    {"label": "Contabo VPS", "host": "root@194.163.146.149"},
]


def _chain(*items: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        ordered.append(clean)
        seen.add(clean)
    return ordered


def _model_ref(provider: str, model: str) -> str:
    clean_provider = str(provider or "").strip()
    clean_model = str(model or "").strip()
    if not clean_provider:
        return clean_model
    if not clean_model:
        return clean_provider
    return f"{clean_provider}::{clean_model}"


def split_model_ref(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if "::" not in raw:
        return ("auto", raw)
    provider, model = raw.split("::", 1)
    return (provider.strip() or "auto", model.strip())


def _speech_target(provider: str, **kwargs) -> dict:
    payload = {"provider": str(provider or "").strip()}
    for key, value in kwargs.items():
        if value in ("", None, [], {}):
            continue
        payload[str(key)] = value
    return payload


def _target_list(*targets: dict) -> list[dict]:
    return [dict(target) for target in targets if isinstance(target, dict) and target.get("provider")]


# --- Legacy Ollama Compatibility ---
# Keep these local fallbacks so older code paths and degraded mode still work.
USE_VPS_OLLAMA = False
VPS_OLLAMA_URL = "http://194.163.146.149:8765/ollama"
VPS_OLLAMA_USER = "butler"
VPS_OLLAMA_PASS = ""      # stored locally in secrets/local_secrets.json
VPS_OLLAMA_MODEL = "gemma4:26b"
VPS_OLLAMA_FALLBACK = "deepseek-r1:14b"

# Use 127.0.0.1 to avoid localhost IPv6 resolution glitches on macOS.
OLLAMA_LOCAL_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma4:e4b"
OLLAMA_FALLBACK = "deepseek-r1:14b"

# --- NVIDIA Provider Surface ---
NVIDIA_API_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_API_KEY_ENV = "NVIDIA_API_KEY"

NVIDIA_CLASSIFIER_MODEL = _model_ref("nvidia", "nvidia/nvidia-nemotron-nano-9b-v2")
NVIDIA_GEMMA_GOD_MODEL = _model_ref("nvidia", "google/gemma-4-31b-it")
NVIDIA_GEMMA_E4B_MODEL = _model_ref("nvidia", "google/gemma-3n-e4b-it")
NVIDIA_GEMMA_MODEL = NVIDIA_GEMMA_E4B_MODEL
NVIDIA_VOICE_MODEL = NVIDIA_GEMMA_E4B_MODEL
NVIDIA_REASONING_MODEL = _model_ref("nvidia", "qwen/qwq-32b")
NVIDIA_REVIEW_MODEL = _model_ref("nvidia", "deepseek-ai/deepseek-r1-distill-qwen-32b")
NVIDIA_CODING_MODEL = _model_ref("nvidia", "qwen/qwen2.5-coder-32b-instruct")

NVIDIA_RIVA_SERVER = "grpc.nvcf.nvidia.com:443"
NVIDIA_RIVA_USE_SSL = True
NVIDIA_RIVA_TTS_FUNCTION_ID = "877104f7-e885-42b9-8de8-f6e4c6303969"
NVIDIA_RIVA_TTS_MODEL = "magpie-tts-multilingual"
NVIDIA_RIVA_TTS_VOICE = "Magpie-Multilingual.EN-US.Aria"
NVIDIA_RIVA_TTS_LANGUAGE_CODE = "auto"
NVIDIA_RIVA_TTS_DEFAULT_LANGUAGE_CODE = "en-US"
NVIDIA_RIVA_TTS_HINDI_LANGUAGE_CODE = "hi-IN"
NVIDIA_RIVA_TTS_SAMPLE_RATE_HZ = 44100
NVIDIA_RIVA_ASR_FUNCTION_ID = "71203149-d3b7-4460-8231-1be2543a1fca"
NVIDIA_RIVA_ASR_MODEL = "parakeet-1.1b-rnnt-multilingual-asr"
NVIDIA_RIVA_ASR_LANGUAGE_CODE = "en-US"

# --- Provider Metadata ---
MODEL_PROVIDER_ENDPOINTS = {
    "ollama_local": {
        "kind": "ollama",
        "base_url": OLLAMA_LOCAL_URL,
        "health_url": "",
    },
    "ollama_vps": {
        "kind": "ollama",
        "base_url": VPS_OLLAMA_URL,
        "health_url": "",
        "auth": "basic",
        "user": VPS_OLLAMA_USER,
        "password": VPS_OLLAMA_PASS,
        "secret_name": "ollama",
    },
    "nvidia": {
        "kind": "openai",
        "base_url": NVIDIA_API_BASE_URL,
        "api_key_env": NVIDIA_API_KEY_ENV,
    },
}

SPEECH_PROVIDER_ENDPOINTS = {
    "kokoro": {"kind": "local_tts"},
    "edge": {"kind": "local_tts"},
    "say": {"kind": "local_tts"},
    "mlx": {"kind": "local_stt"},
    "faster": {"kind": "local_stt"},
    "nvidia_riva_tts": {
        "kind": "nvidia_riva_tts",
        "server": NVIDIA_RIVA_SERVER,
        "use_ssl": NVIDIA_RIVA_USE_SSL,
        "api_key_env": NVIDIA_API_KEY_ENV,
    },
    "nvidia_riva_asr": {
        "kind": "nvidia_riva_asr",
        "server": NVIDIA_RIVA_SERVER,
        "use_ssl": NVIDIA_RIVA_USE_SSL,
        "api_key_env": NVIDIA_API_KEY_ENV,
    },
}

# --- Butler Stage Models ---
# Higher-level logic should only ask for a role. Swapping providers should stay here.
INTENT_CLASSIFIER_MODEL = NVIDIA_CLASSIFIER_MODEL
STARTUP_BRIEFING_MODEL = NVIDIA_REASONING_MODEL
BUTLER_MODELS = {
    "voice": NVIDIA_VOICE_MODEL,
    "planning": NVIDIA_REASONING_MODEL,
    "vision": _model_ref("ollama_local", "llama3.2-vision"),
    "review": NVIDIA_REVIEW_MODEL,
    "coding": NVIDIA_CODING_MODEL,
}
CONVERSATION_MODEL = BUTLER_MODELS["voice"]
SMART_REPLY_MODEL = BUTLER_MODELS["voice"]
STRUCTURED_EXTRACTION_MODEL = INTENT_CLASSIFIER_MODEL
TOOL_SUMMARIZER_MODEL = BUTLER_MODELS["voice"]

BUTLER_MODEL_CHAINS = {
    "voice": _chain(
        BUTLER_MODELS["voice"],
        NVIDIA_GEMMA_E4B_MODEL,
        NVIDIA_CLASSIFIER_MODEL,
        _model_ref("ollama_local", "gemma4:e4b"),
        _model_ref("ollama_local", "deepseek-r1:14b"),
    ),
    "planning": _chain(
        BUTLER_MODELS["planning"],
        NVIDIA_GEMMA_GOD_MODEL,
        NVIDIA_REVIEW_MODEL,
        NVIDIA_GEMMA_E4B_MODEL,
        NVIDIA_CLASSIFIER_MODEL,
        _model_ref("ollama_vps", "gemma4:26b"),
        _model_ref("ollama_local", "gemma4:e4b"),
        _model_ref("ollama_local", "deepseek-r1:14b"),
    ),
    "vision": _chain(
        BUTLER_MODELS["vision"],
        _model_ref("ollama_local", "gemma4:e4b"),
        _model_ref("ollama_local", "deepseek-r1:14b"),
    ),
    "review": _chain(
        BUTLER_MODELS["review"],
        NVIDIA_GEMMA_E4B_MODEL,
        NVIDIA_REASONING_MODEL,
        NVIDIA_GEMMA_GOD_MODEL,
        NVIDIA_CLASSIFIER_MODEL,
        _model_ref("ollama_vps", "gemma4:26b"),
        _model_ref("ollama_local", "gemma4:e4b"),
        _model_ref("ollama_local", "deepseek-r1:14b"),
    ),
    "coding": _chain(
        BUTLER_MODELS["coding"],
        NVIDIA_REASONING_MODEL,
        NVIDIA_GEMMA_GOD_MODEL,
        NVIDIA_REVIEW_MODEL,
        NVIDIA_GEMMA_E4B_MODEL,
        _model_ref("ollama_vps", "gemma4:26b"),
        _model_ref("ollama_local", "gemma4:e4b"),
        _model_ref("ollama_local", "deepseek-r1:14b"),
    ),
}

# --- Multi-Agent Models ---
AGENT_MODELS = {
    "news": NVIDIA_GEMMA_E4B_MODEL,
    "market": NVIDIA_GEMMA_E4B_MODEL,
    "hackernews": NVIDIA_VOICE_MODEL,
    "reddit": NVIDIA_VOICE_MODEL,
    "github_trending": NVIDIA_VOICE_MODEL,
    "vps": NVIDIA_CODING_MODEL,
    "memory": NVIDIA_VOICE_MODEL,
    "code": NVIDIA_CODING_MODEL,
    "search": NVIDIA_GEMMA_E4B_MODEL,
    "github": NVIDIA_CODING_MODEL,
    "bugfinder": NVIDIA_REVIEW_MODEL,
}

AGENT_MODEL_CHAINS = {
    "news": _chain(AGENT_MODELS["news"], NVIDIA_REASONING_MODEL, NVIDIA_REVIEW_MODEL, NVIDIA_GEMMA_GOD_MODEL, NVIDIA_CLASSIFIER_MODEL, _model_ref("ollama_vps", "gemma4:26b"), _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "market": _chain(AGENT_MODELS["market"], NVIDIA_REASONING_MODEL, BUTLER_MODELS["review"], NVIDIA_GEMMA_GOD_MODEL, _model_ref("ollama_vps", "gemma4:26b"), _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "hackernews": _chain(AGENT_MODELS["hackernews"], NVIDIA_GEMMA_E4B_MODEL, NVIDIA_CLASSIFIER_MODEL, _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "reddit": _chain(AGENT_MODELS["reddit"], NVIDIA_GEMMA_E4B_MODEL, NVIDIA_CLASSIFIER_MODEL, _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "github_trending": _chain(AGENT_MODELS["github_trending"], NVIDIA_GEMMA_E4B_MODEL, NVIDIA_CLASSIFIER_MODEL, _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "vps": _chain(AGENT_MODELS["vps"], BUTLER_MODELS["coding"], NVIDIA_GEMMA_GOD_MODEL, NVIDIA_REASONING_MODEL, NVIDIA_REVIEW_MODEL, NVIDIA_GEMMA_E4B_MODEL, _model_ref("ollama_vps", "gemma4:26b"), _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "memory": _chain(AGENT_MODELS["memory"], NVIDIA_GEMMA_E4B_MODEL, NVIDIA_CLASSIFIER_MODEL, _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "code": _chain(AGENT_MODELS["code"], NVIDIA_GEMMA_GOD_MODEL, NVIDIA_REASONING_MODEL, NVIDIA_REVIEW_MODEL, NVIDIA_GEMMA_E4B_MODEL, _model_ref("ollama_vps", "gemma4:26b"), _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "search": _chain(AGENT_MODELS["search"], NVIDIA_REASONING_MODEL, BUTLER_MODELS["review"], NVIDIA_GEMMA_GOD_MODEL, _model_ref("ollama_vps", "gemma4:26b"), _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "github": _chain(AGENT_MODELS["github"], BUTLER_MODELS["coding"], NVIDIA_GEMMA_GOD_MODEL, NVIDIA_REASONING_MODEL, NVIDIA_GEMMA_E4B_MODEL, _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
    "bugfinder": _chain(AGENT_MODELS["bugfinder"], NVIDIA_GEMMA_E4B_MODEL, NVIDIA_REASONING_MODEL, NVIDIA_GEMMA_GOD_MODEL, _model_ref("ollama_local", "gemma4:e4b"), _model_ref("ollama_local", "deepseek-r1:14b")),
}

# --- MCP Servers ---
# These are optional. Butler keeps working if they are disabled or missing.
# If the upstream package name changes, only update the command here.
MCP_SERVERS = {
    "brave": {
        "enabled": False,
        "transport": "stdio",
        "command": ["npx", "-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": ""},
        "tool_hints": ["search", "brave"],
    },
    "github": {
        "enabled": False,
        "transport": "stdio",
        "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        "tool_hints": ["pull", "issue", "repo", "search"],
    },
}
SEARCH_BACKEND = "auto"
MCP_CONTEXT_ENABLED = True
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:18080").rstrip("/")
EMBED_MODEL = "nomic-embed-text"
TAVILY_API_KEY = ""

# --- Apps ---
SPOTIFY_ENABLED = True
AUTO_PLAY_MUSIC = True
DEFAULT_MUSIC_MODE = "focus"

# --- Voice output ---
TTS_ENGINE = "nvidia_riva_tts"     # "nvidia_riva_tts" | "edge" | "kokoro" | "say" | "auto"
TTS_VOICE = "af_sarah"    # Supported Kokoro voice with cleaner pronunciation than the broken "af" alias
EDGE_TTS_VOICE = "en-US-AvaMultilingualNeural"
EDGE_TTS_RATE = "+0%"
TTS_SPEED = 1.0
TTS_MAX_WORDS = 32        # Hard cap on spoken words
PIPER_MODEL_PATH = ""
PIPER_CONFIG_PATH = ""
TTS_TARGETS = _target_list(
    _speech_target(
        "nvidia_riva_tts",
        model=NVIDIA_RIVA_TTS_MODEL,
        function_id=NVIDIA_RIVA_TTS_FUNCTION_ID,
        voice=NVIDIA_RIVA_TTS_VOICE,
        language_code=NVIDIA_RIVA_TTS_LANGUAGE_CODE,
        sample_rate_hz=NVIDIA_RIVA_TTS_SAMPLE_RATE_HZ,
    ),
    _speech_target("edge", voice=EDGE_TTS_VOICE, rate=EDGE_TTS_RATE),
    _speech_target("kokoro", voice=TTS_VOICE, speed=TTS_SPEED),
    _speech_target("say"),
)

# Backward-compatible aliases for older code/docs.
TTS_BACKEND = TTS_ENGINE
TTS_RATE = 165

# --- Voice input ---
VOICE_FOLLOWUP_ENABLED = True
VOICE_FOLLOWUP_SECONDS = 4.0
VOICE_INPUT_BACKEND = "nvidia_riva_asr"
VOICE_INPUT_MODEL = "mlx-community/whisper-medium-mlx"
VOICE_FASTER_WHISPER_MODEL = "medium.en"
VOICE_INPUT_BEAM_SIZE = 3
VOICE_INPUT_PROMPT = "Transcribe a short English or Hindi voice assistant command. Preserve proper nouns and app names accurately."
STT_SILENCE_THRESHOLD = 0.015
STT_MIN_SPEECH_S = 0.4
STT_MAX_SPEECH_S = 8.0
STT_TARGETS = _target_list(
    _speech_target(
        "nvidia_riva_asr",
        model=NVIDIA_RIVA_ASR_MODEL,
        function_id=NVIDIA_RIVA_ASR_FUNCTION_ID,
        language_code=NVIDIA_RIVA_ASR_LANGUAGE_CODE,
    ),
    _speech_target("mlx", model=VOICE_INPUT_MODEL),
    _speech_target("faster", model=VOICE_FASTER_WHISPER_MODEL, beam_size=VOICE_INPUT_BEAM_SIZE),
)

# --- Heartbeat (KAIROS) ---
HEARTBEAT_ENABLED = True
HEARTBEAT_MODEL = NVIDIA_VOICE_MODEL
HEARTBEAT_INTERVAL_MINUTES = 5
DAILY_INTEL_ENABLED = False

# --- Bug Hunter ---
BUG_HUNTER_ENABLED = True
BUG_HUNTER_MODEL = NVIDIA_REVIEW_MODEL
BUG_HUNTER_INTERVAL_MINUTES = 20
BUG_HUNTER_TARGET_PATH = "~/Burry/mac-butler"

# --- Safety ---
REQUIRE_CONFIRMATION_FOR_PUSH = True
REQUIRE_CONFIRMATION_FOR_DOCKER = True
REQUIRE_CONFIRMATION_FOR_SSH_MUTATIONS = True
REQUIRE_CONFIRMATION_FOR_OVERWRITE = True

# --- Debug ---
VERBOSE_LOGS = False
