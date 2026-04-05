#!/usr/bin/env python3
"""
butler_config.py — edit this to configure your setup.
"""

# --- Paths ---
OBSIDIAN_VAULT_NAME = "Burry"
OBSIDIAN_VAULT_PATH = ""
DEVELOPER_PATH = "~/Developer"
BURRY_PATH = "~/Burry"

# --- VPS ---
VPS_HOSTS = [
    {"label": "Contabo VPS", "host": "root@194.163.146.149"},
]

# --- Orchestrator LLM ---
# Orchestrator handles planning + speech (runs every trigger)
# VPS Ollama offloading
# Set USE_VPS_OLLAMA = True once your VPS is configured.
USE_VPS_OLLAMA = True
VPS_OLLAMA_URL = "http://194.163.146.149:8765/ollama"
VPS_OLLAMA_USER = "butler"
VPS_OLLAMA_PASS = ""      # stored locally in secrets/local_secrets.json
VPS_OLLAMA_MODEL = "llama3.2:3b"
VPS_OLLAMA_FALLBACK = "phi4-mini:latest"

# Local fallback (used when VPS is unreachable)
OLLAMA_LOCAL_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:14b"
OLLAMA_FALLBACK = "llama3.2:3b"

# --- Butler Stage Models ---
# Main Butler flow can route different stages to different models.
BUTLER_MODELS = {
    "voice": "phi4-mini:latest",
    "planning": "qwen2.5-coder:14b",
    "review": "deepseek-r1:14b",
    "coding": "qwen2.5-coder:14b",
}


def _chain(*models: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for model in models:
        if not model or model in seen:
            continue
        ordered.append(model)
        seen.add(model)
    return ordered


BUTLER_MODEL_CHAINS = {
    "voice": _chain(BUTLER_MODELS["voice"], "llama3.2:3b", "llama3:latest", OLLAMA_MODEL),
    "planning": _chain(BUTLER_MODELS["planning"], "deepseek-r1:14b", "glm-4.7-flash:latest", "deepseek-r1:7b", OLLAMA_MODEL),
    "review": _chain(BUTLER_MODELS["review"], "glm-4.7-flash:latest", "deepseek-r1:7b", BUTLER_MODELS["coding"], OLLAMA_MODEL),
    "coding": _chain(BUTLER_MODELS["coding"], "deepseek-r1:14b", "deepseek-coder:6.7b", "glm-4.7-flash:latest", OLLAMA_MODEL),
}

# --- Multi-Agent Models ---
# Specialist agents use smaller/faster models for their specific tasks
# Each falls back to OLLAMA_MODEL if not installed
AGENT_MODELS = {
    "news": "deepseek-r1:14b",
    "vps": "qwen2.5-coder:14b",
    "memory": "phi4-mini:latest",
    "code": "qwen2.5-coder:14b",
    "search": "deepseek-r1:14b",
    "github": "qwen2.5-coder:14b",
    "bugfinder": "qwen2.5-coder:14b",
}

AGENT_MODEL_CHAINS = {
    "news": _chain(AGENT_MODELS["news"], "glm-4.7-flash:latest", "deepseek-r1:7b", OLLAMA_MODEL),
    "vps": _chain(AGENT_MODELS["vps"], "deepseek-coder:6.7b", BUTLER_MODELS["planning"], OLLAMA_MODEL),
    "memory": _chain(AGENT_MODELS["memory"], BUTLER_MODELS["voice"], "llama3.2:3b", OLLAMA_MODEL),
    "code": _chain(AGENT_MODELS["code"], BUTLER_MODELS["coding"], "deepseek-coder:6.7b", "deepseek-r1:14b"),
    "search": _chain(AGENT_MODELS["search"], BUTLER_MODELS["review"], "glm-4.7-flash:latest", "deepseek-r1:7b"),
    "github": _chain(AGENT_MODELS["github"], BUTLER_MODELS["coding"], "deepseek-coder:6.7b", BUTLER_MODELS["planning"]),
    "bugfinder": _chain(AGENT_MODELS["bugfinder"], "deepseek-r1:14b", "deepseek-coder:6.7b", BUTLER_MODELS["review"]),
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
EXA_API_KEY = "43dd4d35-dc20-4a62-af5f-1aa340963c07"
SEARXNG_URL = "http://localhost:8080"
EMBED_MODEL = "nomic-embed-text"
TAVILY_API_KEY = ""

# --- Apps ---
SPOTIFY_ENABLED = True
AUTO_PLAY_MUSIC = True
DEFAULT_MUSIC_MODE = "focus"

# --- Voice output ---
TTS_ENGINE = "kokoro"     # "kokoro" | "say" | "auto"
TTS_VOICE = "af_bella"    # Kokoro voice; fallback `say` uses Daniel automatically
TTS_SPEED = 1.0
TTS_MAX_WORDS = 40        # Hard cap on spoken words
PIPER_MODEL_PATH = ""
PIPER_CONFIG_PATH = ""

# Backward-compatible aliases for older code/docs.
TTS_BACKEND = TTS_ENGINE
TTS_RATE = 165

# --- Voice input ---
VOICE_FOLLOWUP_ENABLED = True
VOICE_FOLLOWUP_SECONDS = 4.0
VOICE_INPUT_MODEL = "mlx-community/whisper-tiny"

# --- Heartbeat (KAIROS) ---
HEARTBEAT_ENABLED = False
HEARTBEAT_INTERVAL_MINUTES = 5

# --- Bug Hunter ---
BUG_HUNTER_ENABLED = False
BUG_HUNTER_INTERVAL_MINUTES = 20
BUG_HUNTER_TARGET_PATH = "~/Burry/mac-butler"

# --- Safety ---
REQUIRE_CONFIRMATION_FOR_PUSH = True
REQUIRE_CONFIRMATION_FOR_DOCKER = True
REQUIRE_CONFIRMATION_FOR_SSH_MUTATIONS = True
REQUIRE_CONFIRMATION_FOR_OVERWRITE = True

# --- Debug ---
VERBOSE_LOGS = False
