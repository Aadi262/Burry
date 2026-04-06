#!/usr/bin/env python3
"""AgentScope backbone for Burry's main orchestration path.

Burry remains the macOS execution layer and UX surface. AgentScope owns the
main ReAct loop, tool calling, short-term memory compression, and tracing.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable

import agentscope
from agentscope.agent import ReActAgent
from agentscope.formatter import OllamaChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg, TextBlock
from agentscope.plan import PlanNotebook
from agentscope.token import CharTokenCounter
from agentscope.tool import ToolResponse, Toolkit as AgentScopeToolkit

from brain.agentscope_ollama_model import BurryOllamaChatModel
from brain.toolkit import get_toolkit as get_burry_toolkit
from butler_config import MCP_SERVERS, OLLAMA_FALLBACK, OLLAMA_LOCAL_URL, OLLAMA_MODEL
from memory.store import get_compressed_context
from runtime import note_tool_finished, note_tool_started

_INIT_LOCK = threading.Lock()
_BACKBONE_LOCK = threading.Lock()
_AGENTSCOPE_READY = False
_BACKBONE: "AgentScopeBackbone | None" = None
_PERSISTENT_LOOP: asyncio.AbstractEventLoop | None = None
_PERSISTENT_LOOP_THREAD: threading.Thread | None = None
_TURN_TOOL_LOG: ContextVar[list[dict[str, Any]] | None] = ContextVar("agentscope_turn_tool_log", default=None)
_TURN_MEMORY_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("agentscope_turn_memory_context", default=None)
_AGENT_SCOPE_SKILLS_DIR = Path(__file__).resolve().parents[1] / "agent_skills"
_INTENT_TOOLKIT_CACHE: dict[str, AgentScopeToolkit] = {}
_AGENT_CACHE: dict[str, ReActAgent] = {}
_MCP_TOOLS_CACHE: dict[str, list[Callable[..., Any]]] = {}
INTENT_TOOLS: dict[str, list[str]] = {
    "question": ["deep_research", "web_search_summarize", "recall_memory"],
    "open_project": ["open_project", "focus_app", "run_shell"],
    "compose_email": ["send_email"],
    "play_music": ["spotify_control"],
    "plan_and_execute": ["open_project", "focus_app", "run_shell", "set_reminder", "git_commit"],
    "what_next": ["recall_memory", "open_project", "focus_app", "run_shell", "web_search_summarize"],
    "default": ["browse_and_act", "recall_memory", "web_search_summarize"],
}
INTENT_TOOL_ALIASES = {
    "greeting": "default",
    "unknown": "default",
    "browser_search": "default",
    "browser_new_tab": "default",
    "compose_mail": "compose_email",
    "spotify_play": "play_music",
    "spotify_pause": "play_music",
    "spotify_next": "play_music",
    "spotify_prev": "play_music",
    "spotify_mode": "play_music",
}
INTENT_CTX: dict[str, int] = {
    "plan_and_execute": 8192,
    "deep_research": 8192,
    "question": 4096,
    "what_next": 4096,
    "default": 2048,
    "greeting": 1024,
    "play_music": 1024,
    "volume_up": 1024,
    "volume_down": 1024,
    "focus_app": 1024,
    "open_project": 2048,
    "compose_email": 2048,
}
PARALLEL_TOOL_INTENTS = {"question", "what_next", "deep_research"}
SPECIALIST_PROMPTS = {
    "search": "You search the web and return a concise factual summary under 30 words.",
    "reddit": "You fetch top Reddit discussions and summarize the key points briefly.",
    "hn": "You fetch Hacker News top stories and summarize the most relevant one.",
    "news": "You fetch latest tech news and summarize the top story in under 25 words.",
    "vps": "You check VPS server status and report CPU, memory, and disk usage concisely.",
}
_SPECIALIST_TOOLS: dict[str, set[str]] = {
    "search": {"browse_web", "web_search_summarize", "browse_and_act"},
    "reddit": {"browse_web", "web_search_summarize"},
    "hn": {"browse_web", "web_search_summarize"},
    "news": {"browse_web", "web_search_summarize"},
    "vps": {"ssh_vps"},
}


def _ollama_agent_host() -> str:
    # The official Ollama Python client on this machine needs an explicit IPv4 host.
    return str(OLLAMA_LOCAL_URL or "http://127.0.0.1:11434").replace("localhost", "127.0.0.1")


def ensure_agentscope_initialized() -> None:
    global _AGENTSCOPE_READY
    if _AGENTSCOPE_READY:
        return
    with _INIT_LOCK:
        if _AGENTSCOPE_READY:
            return
        log_dir = Path(__file__).resolve().parents[1] / "memory" / "agentscope_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        agentscope.init(
            project="burry-os",
            name="main-react-agent",
            logging_path=str(log_dir / "agentscope.log"),
            # If AGENTSCOPE_TRACING_URL is set, AgentScope exports spans there.
            tracing_url=os.environ.get("AGENTSCOPE_TRACING_URL") or None,
        )
        _register_mcp_tools(force_refresh=False)
        _AGENTSCOPE_READY = True


def _get_persistent_loop() -> asyncio.AbstractEventLoop:
    global _PERSISTENT_LOOP, _PERSISTENT_LOOP_THREAD
    if _PERSISTENT_LOOP is None or _PERSISTENT_LOOP.is_closed():
        loop = asyncio.new_event_loop()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        _PERSISTENT_LOOP = loop
        _PERSISTENT_LOOP_THREAD = threading.Thread(
            target=_runner,
            daemon=True,
            name="burry-agentscope-loop",
        )
        _PERSISTENT_LOOP_THREAD.start()
    return _PERSISTENT_LOOP


def _tool_response_text(response: ToolResponse) -> str:
    parts: list[str] = []
    for block in response.content or []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                text = " ".join(str(block.get("text", "")).split()).strip()
                if text:
                    parts.append(text)
            continue
        if getattr(block, "type", None) == "text":
            text = " ".join(str(getattr(block, "text", "")).split()).strip()
            if text:
                parts.append(text)
    return " ".join(parts).strip()


def _as_tool_response(result: Any, metadata: dict[str, Any] | None = None) -> ToolResponse:
    if isinstance(result, ToolResponse):
        if metadata and result.metadata is not None:
            result.metadata.update(metadata)
        elif metadata and result.metadata is None:
            result.metadata = dict(metadata)
        return result
    text = " ".join(str(result or "").split()).strip() or "Done."
    return ToolResponse(
        content=[TextBlock(type="text", text=text)],
        metadata=dict(metadata or {}),
    )


def _register_agent_skills(toolkit: AgentScopeToolkit) -> None:
    if not _AGENT_SCOPE_SKILLS_DIR.exists():
        return
    for skill_dir in sorted(_AGENT_SCOPE_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        try:
            toolkit.register_agent_skill(str(skill_dir))
        except Exception:
            continue


def _wrap_local_tool(tool_name: str, func):
    async def _wrapped_tool(**kwargs):
        if inspect.iscoroutinefunction(func):
            result = await func(**kwargs)
        else:
            result = await asyncio.to_thread(func, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        return _as_tool_response(result, metadata={"tool": tool_name})

    _wrapped_tool.__name__ = tool_name
    _wrapped_tool.__doc__ = getattr(func, "__doc__", "") or f"Burry tool {tool_name}"
    _wrapped_tool.__annotations__ = getattr(func, "__annotations__", {})
    return _wrapped_tool


def _build_mcp_tool(server_name: str, tool_name: str):
    async def _mcp_tool(**kwargs):
        from burry_mcp import call_server_tool, normalize_tool_result

        result = call_server_tool(
            server_name,
            arguments=kwargs,
            preferred_tool=tool_name,
        )
        return _as_tool_response(
            normalize_tool_result(result) or f"{server_name}.{tool_name} completed",
            metadata={"tool": tool_name, "server": server_name},
        )

    _mcp_tool.__name__ = f"mcp_{server_name}_{tool_name}"
    _mcp_tool.__doc__ = f"MCP tool {tool_name} from {server_name}"
    return _mcp_tool


def _scan_mcp_server(server_name: str, _server_config: dict | None = None) -> list[Callable[..., Any]]:
    from burry_mcp import list_server_tools

    tools = list_server_tools(server_name)
    loaded: list[Callable[..., Any]] = []
    for tool_info in tools:
        tool_name = str(tool_info.get("name", "")).strip()
        if not tool_name:
            continue
        loaded.append(_build_mcp_tool(server_name, tool_name))
    return loaded


def _register_mcp_tools(
    toolkit: AgentScopeToolkit | None = None,
    force_refresh: bool = False,
) -> None:
    global _MCP_TOOLS_CACHE

    if _MCP_TOOLS_CACHE and not force_refresh:
        if toolkit is None:
            return
        for funcs in _MCP_TOOLS_CACHE.values():
            for func in funcs:
                try:
                    toolkit.register_tool_function(func, namesake_strategy="override")
                except Exception:
                    continue
        return

    _MCP_TOOLS_CACHE = {}
    for server_name, server_config in MCP_SERVERS.items():
        try:
            funcs = _scan_mcp_server(server_name, server_config)
            _MCP_TOOLS_CACHE[server_name] = funcs
            if toolkit is None:
                continue
            for func in funcs:
                toolkit.register_tool_function(func, namesake_strategy="override")
        except Exception as exc:
            print(f"[MCP] Failed to load {server_name}: {exc}")


def _make_post_reply_hook(ctx: dict | None = None):
    def on_post_reply(output_msg, _agent):
        """Write the final assistant reply into long-term working memory."""
        try:
            from memory.long_term import add_to_working_memory

            active_ctx = ctx or _TURN_MEMORY_CONTEXT.get() or {}
            heard = " ".join(
                str(active_ctx.get("last_heard") or active_ctx.get("heard") or "").split()
            ).strip()
            spoken = (
                output_msg.get_text_content()
                if hasattr(output_msg, "get_text_content")
                else str(output_msg or "")
            )
            spoken = " ".join(str(spoken).split()).strip()
            if heard and spoken:
                add_to_working_memory(heard, spoken)
        except Exception:
            pass
        return output_msg

    return on_post_reply


async def _tool_logging_middleware(kwargs: dict, next_handler):
    tool_call = kwargs.get("tool_call", {}) or {}
    tool_name = str(tool_call.get("name", "")).strip() or "unknown_tool"
    tool_input = dict(tool_call.get("input", {}) or {})
    entry = {
        "tool": tool_name,
        "input": tool_input,
        "status": "ok",
        "result": "",
    }
    note_tool_started(tool_name, str(tool_input)[:180])
    try:
        async for response in await next_handler(**kwargs):
            text = _tool_response_text(response)
            if text:
                entry["result"] = text
            yield response
    except Exception as exc:
        entry["status"] = "error"
        entry["result"] = str(exc)
        note_tool_finished(tool_name, "error", str(exc)[:200])
        tool_log = _TURN_TOOL_LOG.get()
        if tool_log is not None:
            tool_log.append(entry)
        raise
    else:
        note_tool_finished(tool_name, entry["status"], entry["result"][:200])
        tool_log = _TURN_TOOL_LOG.get()
        if tool_log is not None:
            tool_log.append(entry)


def build_agentscope_toolkit(
    *,
    include_tools: set[str] | None = None,
    exclude_tools: set[str] | None = None,
    include_mcp: bool = True,
    include_skills: bool = True,
    include_middleware: bool = True,
) -> AgentScopeToolkit:
    import brain.tools_registry  # noqa: F401

    source = get_burry_toolkit()
    toolkit = AgentScopeToolkit()
    excluded = {name for name in (exclude_tools or set()) if name}
    included = {name for name in (include_tools or set()) if name}

    for tool_name, func in source._tools.items():
        if included and tool_name not in included:
            continue
        if tool_name in excluded:
            continue
        toolkit.register_tool_function(
            _wrap_local_tool(tool_name, func),
            async_execution=True,
            namesake_strategy="override",
        )

    if include_middleware:
        toolkit.register_middleware(_tool_logging_middleware)
    if include_mcp:
        _register_mcp_tools(toolkit)
    if include_skills:
        _register_agent_skills(toolkit)
    return toolkit


def _build_agentscope_toolkit() -> AgentScopeToolkit:
    return build_agentscope_toolkit()


def _get_num_ctx(intent_name: str | None) -> int:
    raw = str(intent_name or "").strip().lower()
    if raw in INTENT_CTX:
        return INTENT_CTX[raw]
    key = _intent_tool_key(raw or "default")
    return INTENT_CTX.get(key, INTENT_CTX["default"])


def _compression_config(
    model_name: str,
    intent_name: str | None = None,
) -> ReActAgent.CompressionConfig:
    compression_model_name = OLLAMA_FALLBACK or model_name or OLLAMA_MODEL
    num_ctx = _get_num_ctx(intent_name)
    compression_model = BurryOllamaChatModel(
        model_name=compression_model_name,
        host=_ollama_agent_host(),
        stream=False,
        options={"temperature": 0.1, "num_ctx": num_ctx},
    )
    compression_formatter = OllamaChatFormatter(max_tokens=num_ctx)
    return ReActAgent.CompressionConfig(
        enable=True,
        agent_token_counter=CharTokenCounter(),
        trigger_threshold=12000,
        keep_recent=6,
        compression_model=compression_model,
        compression_formatter=compression_formatter,
    )


def _intent_tool_key(intent_name: str | None) -> str:
    raw = str(intent_name or "").strip().lower()
    if not raw:
        return "default"
    normalized = INTENT_TOOL_ALIASES.get(raw, raw)
    return normalized if normalized in INTENT_TOOLS else "default"


def _tool_names_for_intent(intent_name: str | None) -> set[str]:
    return set(INTENT_TOOLS.get(_intent_tool_key(intent_name), INTENT_TOOLS["default"]))


def _build_filtered_toolkit(source_toolkit, tool_names: list[str]) -> AgentScopeToolkit:
    """Build a reusable AgentScope toolkit with only the selected Burry tools."""
    filtered = AgentScopeToolkit()
    allowed = set(tool_names)
    for tool_name, func in getattr(source_toolkit, "_tools", {}).items():
        if tool_name not in allowed:
            continue
        filtered.register_tool_function(
            _wrap_local_tool(tool_name, func),
            async_execution=True,
            namesake_strategy="override",
        )
    filtered.register_middleware(_tool_logging_middleware)
    if allowed & {"send_email", "send_imessage"}:
        _register_agent_skills(filtered)
    return filtered


def get_tools_for_intent(
    intent_name: str | None,
    full_toolkit=None,
) -> AgentScopeToolkit:
    """Return a cached toolkit for this intent. Build once, reuse forever."""
    key = _intent_tool_key(intent_name or "default")
    if key not in _INTENT_TOOLKIT_CACHE:
        source_toolkit = full_toolkit or get_burry_toolkit()
        tool_names = INTENT_TOOLS.get(key, INTENT_TOOLS.get("default", []))
        _INTENT_TOOLKIT_CACHE[key] = _build_filtered_toolkit(source_toolkit, tool_names)
    return _INTENT_TOOLKIT_CACHE[key]


def _use_plan_notebook(intent_name: str | None) -> bool:
    return _intent_tool_key(intent_name) == "plan_and_execute"


def create_react_agent(
    *,
    name: str,
    system_prompt: str,
    model_name: str,
    intent_name: str | None = None,
    toolkit: AgentScopeToolkit | None = None,
    memory: InMemoryMemory | None = None,
    plan_notebook: PlanNotebook | None = None,
    parallel_tool_calls: bool = False,
    max_iters: int = 6,
    stream: bool = False,
) -> ReActAgent:
    ensure_agentscope_initialized()
    num_ctx = _get_num_ctx(intent_name)
    agent = ReActAgent(
        name=name,
        sys_prompt=system_prompt,
        model=BurryOllamaChatModel(
            model_name=model_name,
            host=_ollama_agent_host(),
            stream=stream,
            options={"temperature": 0.2, "num_ctx": num_ctx},
            keep_alive="5m",
        ),
        formatter=OllamaChatFormatter(max_tokens=num_ctx),
        toolkit=toolkit or _build_agentscope_toolkit(),
        memory=memory or InMemoryMemory(),
        parallel_tool_calls=parallel_tool_calls,
        max_iters=max_iters,
        plan_notebook=plan_notebook,
        compression_config=_compression_config(model_name, intent_name),
    )
    agent.set_console_output_enabled(False)
    if not getattr(agent, "_burry_post_reply_hook_registered", False):
        agent.register_instance_hook(
            "post_reply",
            "burry-memory-writeback",
            _make_post_reply_hook(),
        )
        agent._burry_post_reply_hook_registered = True  # type: ignore[attr-defined]
    return agent


def _make_specialist_agent(name: str):
    ensure_agentscope_initialized()
    specialist_tools = _SPECIALIST_TOOLS.get(name, {"browse_web", "web_search_summarize"})
    return ReActAgent(
        name=name,
        sys_prompt=SPECIALIST_PROMPTS.get(name, "You are a helpful specialist agent."),
        model=BurryOllamaChatModel(
            model_name=OLLAMA_MODEL,
            host=_ollama_agent_host(),
            stream=False,
            options={"temperature": 0.2, "num_ctx": 1024},
        ),
        formatter=OllamaChatFormatter(max_tokens=512),
        toolkit=build_agentscope_toolkit(
            include_tools=specialist_tools,
            include_mcp=False,
            include_skills=False,
            include_middleware=False,
        ),
        memory=InMemoryMemory(),
        max_iters=3,
    )


class AgentScopeBackbone:
    def __init__(self, model_name: str):
        ensure_agentscope_initialized()
        self.model_name = model_name
        self._intent_key = "default"
        self._stream_enabled = False
        self._active_loop: asyncio.AbstractEventLoop | None = None
        self._interrupt_requested = False
        self.memory = InMemoryMemory()
        self.agent = self._build_agent(model_name, stream=False, intent_name="default")

    def _build_agent(self, model_name: str, *, stream: bool, intent_name: str) -> ReActAgent:
        from memory.long_term import restore_session_state

        agent = create_react_agent(
            name="Burry",
            system_prompt="You are Burry, a macOS operator agent.",
            model_name=model_name,
            intent_name=intent_name,
            toolkit=get_tools_for_intent(intent_name),
            memory=self.memory,
            plan_notebook=PlanNotebook(max_subtasks=8) if _use_plan_notebook(intent_name) else None,
            parallel_tool_calls=_intent_tool_key(intent_name) in PARALLEL_TOOL_INTENTS,
            max_iters=6,
            stream=stream,
        )
        restore_session_state(agent)
        agent.set_msg_queue_enabled(stream)
        return agent

    def _ensure_model(self, model_name: str | None, *, stream: bool, intent_name: str) -> None:
        resolved = str(model_name or "").strip() or self.model_name
        intent_key = _intent_tool_key(intent_name)
        cache_key = f"{intent_key}:{resolved}"
        if cache_key not in _AGENT_CACHE:
            _AGENT_CACHE[cache_key] = self._build_agent(
                resolved,
                stream=stream,
                intent_name=intent_key,
            )
        self.model_name = resolved
        self._intent_key = intent_key
        self._stream_enabled = stream
        self.agent = _AGENT_CACHE[cache_key]
        self.memory = getattr(self.agent, "memory", self.memory)
        try:
            self.agent.model.stream = stream
        except Exception:
            pass
        self.agent.set_msg_queue_enabled(stream)

    @staticmethod
    def _text_delta(previous: str, current: str) -> str:
        if not previous:
            return current
        if current.startswith(previous):
            return current[len(previous):]
        match_len = 0
        max_len = min(len(previous), len(current))
        while match_len < max_len and previous[match_len] == current[match_len]:
            match_len += 1
        return current[match_len:]

    async def _iter_streamed_sentences(self, reply_task: asyncio.Task) -> Any:
        from brain.ollama_client import _yield_complete_sentences

        queue = self.agent.msg_queue
        if queue is None:
            return

        buffered_text = ""
        seen_text = ""

        while True:
            if reply_task.done() and queue.empty():
                break
            try:
                msg, last, _speech = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            try:
                if self._interrupt_requested:
                    continue

                if not isinstance(msg, Msg):
                    continue

                current_text = str(msg.get_text_content(separator=" ") or "")
                current_text = " ".join(current_text.split())
                if current_text:
                    delta = self._text_delta(seen_text, current_text)
                    if delta:
                        buffered_text += delta
                        sentences, buffered_text = _yield_complete_sentences(buffered_text)
                        for sentence in sentences:
                            cleaned = " ".join(str(sentence).split()).strip()
                            if cleaned:
                                yield cleaned
                    seen_text = current_text

                if last and buffered_text.strip():
                    cleaned = " ".join(buffered_text.split()).strip()
                    if cleaned:
                        yield cleaned
                    buffered_text = ""
            finally:
                queue.task_done()

        if buffered_text.strip():
            yield " ".join(buffered_text.split()).strip()

    async def _forward_streamed_sentences(
        self,
        reply_task: asyncio.Task,
        on_sentence: Callable[[str], None],
    ) -> None:
        async for sentence in self._iter_streamed_sentences(reply_task):
            if self._interrupt_requested:
                return
            try:
                on_sentence(sentence)
            except Exception:
                continue

    def interrupt(self, new_command: str) -> bool:
        loop = self._active_loop
        if loop is None or not loop.is_running():
            return False
        self._interrupt_requested = True
        try:
            reply_task = getattr(self.agent, "_reply_task", None)
            if reply_task is not None and not reply_task.done():
                future = asyncio.run_coroutine_threadsafe(
                    self.agent.interrupt(Msg("user", new_command, "user")),
                    loop,
                )
                future.add_done_callback(lambda fut: fut.exception())
            return True
        except Exception:
            return False

    def _system_prompt(self, ctx: dict, system_prompt: str) -> str:
        formatted = str(ctx.get("formatted", "") or "").strip()
        compressed = get_compressed_context(max_tokens=1800)
        parts = [
            system_prompt.strip(),
            "Control-plane rules:",
            "- You are the single main ReAct agent for Burry.",
            "- Use tools for real actions instead of describing them.",
            "- Burry's clap, wake, HUD, and macOS execution layer are external runtime surfaces, not separate agents.",
            "- Keep the final spoken answer concise and operator-friendly.",
        ]
        if formatted:
            parts.extend(["[CURRENT WORKSPACE CONTEXT]", formatted[:3000]])
        if compressed:
            parts.extend(["[COMPRESSED MEMORY CONTEXT]", compressed[:1800]])
        return "\n\n".join(part for part in parts if part)

    async def run_turn(
        self,
        text: str,
        ctx: dict,
        *,
        system_prompt: str,
        model_name: str | None = None,
        intent_name: str = "default",
        stream_speech: bool = False,
        on_sentence: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        self._interrupt_requested = False
        self._active_loop = asyncio.get_running_loop()
        self._ensure_model(model_name, stream=stream_speech, intent_name=intent_name)
        self.agent._sys_prompt = self._system_prompt(ctx, system_prompt)  # noqa: SLF001
        compressed = get_compressed_context(max_tokens=1800)
        if compressed:
            try:
                result = self.memory.update_compressed_summary(compressed)
                if asyncio.iscoroutine(result):
                    await result
            except (AttributeError, TypeError):
                pass

        tool_log: list[dict[str, Any]] = []
        token = _TURN_TOOL_LOG.set(tool_log)
        memory_ctx = dict(ctx or {})
        if text and not memory_ctx.get("last_heard"):
            memory_ctx["last_heard"] = text
        memory_token = _TURN_MEMORY_CONTEXT.set(memory_ctx)
        self.agent.set_msg_queue_enabled(stream_speech and callable(on_sentence))
        reply_task: asyncio.Task | None = None
        stream_task: asyncio.Task | None = None
        try:
            user_msg = Msg(
                "user",
                text,
                "user",
                metadata={
                    "focus_project": str(ctx.get("focus_project", "") or ""),
                    "workspace": str(ctx.get("workspace", "") or ""),
                },
            )
            reply_task = asyncio.create_task(self.agent(user_msg))
            if self._interrupt_requested:
                await asyncio.sleep(0)
                await self.agent.interrupt(Msg("user", "Interrupt requested.", "user"))
            if stream_speech and callable(on_sentence):
                stream_task = asyncio.create_task(
                    self._forward_streamed_sentences(reply_task, on_sentence),
                )
            reply = await reply_task
            if stream_task is not None:
                await stream_task
        finally:
            if stream_task is not None and not stream_task.done():
                stream_task.cancel()
            self.agent.set_msg_queue_enabled(False)
            self._active_loop = None
            _TURN_MEMORY_CONTEXT.reset(memory_token)
            _TURN_TOOL_LOG.reset(token)

        interrupted = bool(getattr(reply, "metadata", {}) and reply.metadata.get("_is_interrupted"))
        speech = "" if interrupted else " ".join(str(reply.get_text_content() or "").split()).strip()
        actions = [{"type": entry["tool"], **entry["input"]} for entry in tool_log]
        results = [
            {
                "action": entry["tool"],
                "status": entry["status"],
                "result": entry["result"],
            }
            for entry in tool_log
        ]
        return {
            "speech": speech,
            "actions": actions,
            "results": results,
            "metadata": {
                **dict(reply.metadata or {}),
                "interrupted": interrupted,
                "spoken": bool(stream_speech and on_sentence and speech),
            },
        }


def _default_model_name() -> str:
    return str(OLLAMA_FALLBACK or OLLAMA_MODEL).strip() or "gemma4:e4b"


def get_backbone(model_name: str | None = None) -> AgentScopeBackbone:
    global _BACKBONE
    resolved = str(model_name or "").strip() or _default_model_name()
    with _BACKBONE_LOCK:
        if _BACKBONE is None:
            _BACKBONE = AgentScopeBackbone(resolved)
        return _BACKBONE


def run_agentscope_turn(
    text: str,
    ctx: dict,
    *,
    system_prompt: str,
    model_name: str | None = None,
    intent_name: str = "default",
    stream_speech: bool = False,
    on_sentence: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    backbone = get_backbone(model_name=model_name)
    loop = _get_persistent_loop()
    future = asyncio.run_coroutine_threadsafe(
        backbone.run_turn(
            text,
            ctx,
            system_prompt=system_prompt,
            model_name=model_name,
            intent_name=intent_name,
            stream_speech=stream_speech,
            on_sentence=on_sentence,
        ),
        loop,
    )
    return future.result(timeout=90)


def interrupt_agentscope_turn(new_command: str) -> bool:
    try:
        backbone = get_backbone()
    except Exception:
        return False
    return backbone.interrupt(new_command)
