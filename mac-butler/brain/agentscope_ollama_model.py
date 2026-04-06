#!/usr/bin/env python3
"""AgentScope-compatible Ollama model adapter using Burry's HTTP client path."""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from datetime import datetime
from typing import Any, AsyncGenerator, Literal, Type

import httpx
from pydantic import BaseModel

from agentscope.message import TextBlock, ThinkingBlock, ToolUseBlock
from agentscope.model import ChatResponse, OllamaChatModel
from agentscope.model._model_usage import ChatUsage
from agentscope.tracing import trace_llm
from agentscope._utils._common import _json_loads_with_repair

from brain.ollama_client import _get_request_target_for_model, _prepare_model_request, _resolve_backend_model, chat_with_ollama


class BurryOllamaChatModel(OllamaChatModel):
    """Drop-in replacement for AgentScope's Ollama model.

    The official Ollama Python client streams unreliably in this environment.
    This adapter keeps AgentScope's model abstraction intact while routing all
    requests through the repo's existing HTTP code path.
    """

    def _merged_options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        options = dict(self.options or {})
        extra = kwargs.pop("options", None)
        if isinstance(extra, dict):
            options.update(extra)
        return options

    @trace_llm
    async def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        structured_model: Type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        if tool_choice:
            # Ollama ignores this anyway; keep parity with the upstream class.
            pass

        options = self._merged_options(kwargs)
        formatted_tools = self._format_tools_json_schemas(tools) if tools else None
        start_datetime = datetime.now()

        if self.stream:
            return self._stream_chat(
                start_datetime=start_datetime,
                messages=messages,
                tools=formatted_tools,
                structured_model=structured_model,
                options=options,
            )

        return await asyncio.to_thread(
            self._chat_once,
            start_datetime,
            messages,
            formatted_tools,
            structured_model,
            options,
        )

    def _chat_once(
        self,
        start_datetime: datetime,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        structured_model: Type[BaseModel] | None,
        options: dict[str, Any],
    ) -> ChatResponse:
        data = chat_with_ollama(
            messages,
            self.model_name,
            tools=tools,
            max_tokens=int(options.get("num_predict", 300) or 300),
            temperature=float(options.get("temperature", 0.2) or 0.2),
        )
        return self._parse_http_response(
            start_datetime=start_datetime,
            response=data,
            structured_model=structured_model,
        )

    async def _stream_chat(
        self,
        *,
        start_datetime: datetime,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        structured_model: Type[BaseModel] | None,
        options: dict[str, Any],
    ) -> AsyncGenerator[ChatResponse, None]:
        url, headers, backend = _get_request_target_for_model(self.model_name)
        request_url = url.replace("/api/generate", "/api/chat")
        use_vps_backend = backend == "vps"
        resolved_model = _resolve_backend_model(self.model_name, use_vps_backend)
        _prepare_model_request(resolved_model)

        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": options,
            **self.generate_kwargs,
        }
        if self.think is not None and "think" not in payload:
            payload["think"] = self.think
        if tools:
            payload["tools"] = tools
        if structured_model:
            payload["format"] = structured_model.model_json_schema()

        accumulated_text = ""
        accumulated_thinking = ""
        tool_calls: OrderedDict[str, dict[str, Any]] = OrderedDict()
        metadata: dict | None = None
        response_id: str | None = None

        timeout = httpx.Timeout(connect=5.0, read=90.0, write=15.0, pool=None)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", request_url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except Exception:
                        continue

                    message = chunk.get("message", {}) or {}
                    accumulated_thinking += str(message.get("thinking", "") or "")
                    accumulated_text += str(message.get("content", "") or "")

                    for idx, tool_call in enumerate(message.get("tool_calls") or []):
                        function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                        tool_name = str(function.get("name", "") or "")
                        if not tool_name:
                            continue
                        tool_id = f"{idx}_{tool_name}"
                        tool_calls[tool_id] = {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": function.get("arguments", {}),
                            "raw_input": json.dumps(function.get("arguments", {})),
                        }

                    usage = ChatUsage(
                        input_tokens=int(chunk.get("prompt_eval_count", 0) or 0),
                        output_tokens=int(chunk.get("eval_count", 0) or 0),
                        time=(datetime.now() - start_datetime).total_seconds(),
                    )

                    content: list[Any] = []
                    if accumulated_thinking:
                        content.append(
                            ThinkingBlock(
                                type="thinking",
                                thinking=accumulated_thinking,
                            ),
                        )
                    if accumulated_text:
                        content.append(
                            TextBlock(
                                type="text",
                                text=accumulated_text,
                            ),
                        )
                        if structured_model:
                            metadata = _json_loads_with_repair(accumulated_text)
                    for tool_call in tool_calls.values():
                        input_data = tool_call["input"]
                        if isinstance(input_data, str):
                            input_data = _json_loads_with_repair(input_data)
                        content.append(
                            ToolUseBlock(
                                type="tool_use",
                                id=tool_call["id"],
                                name=tool_call["name"],
                                input=input_data,
                                raw_input=tool_call["raw_input"],
                            ),
                        )

                    if response_id is None:
                        response_id = str(chunk.get("id", "") or "") or None

                    if chunk.get("done") or content:
                        kwargs: dict[str, Any] = {
                            "content": content,
                            "usage": usage,
                            "metadata": metadata,
                        }
                        if response_id:
                            kwargs["id"] = response_id
                        yield ChatResponse(**kwargs)

    def _parse_http_response(
        self,
        *,
        start_datetime: datetime,
        response: dict[str, Any],
        structured_model: Type[BaseModel] | None,
    ) -> ChatResponse:
        message = response.get("message", {}) if isinstance(response, dict) else {}
        content_blocks: list[Any] = []
        metadata: dict | None = None

        thinking = str(message.get("thinking", "") or "")
        if thinking:
            content_blocks.append(
                ThinkingBlock(
                    type="thinking",
                    thinking=thinking,
                ),
            )

        text = str(message.get("content", "") or "")
        if text:
            content_blocks.append(
                TextBlock(
                    type="text",
                    text=text,
                ),
            )
            if structured_model:
                metadata = _json_loads_with_repair(text)

        for idx, tool_call in enumerate(message.get("tool_calls") or []):
            function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
            args = function.get("arguments", {})
            if isinstance(args, str):
                args = _json_loads_with_repair(args)
            content_blocks.append(
                ToolUseBlock(
                    type="tool_use",
                    id=f"{idx}_{function.get('name', 'tool')}",
                    name=str(function.get("name", "") or "tool"),
                    input=args,
                    raw_input=json.dumps(args),
                ),
            )

        usage = ChatUsage(
            input_tokens=int(response.get("prompt_eval_count", 0) or 0),
            output_tokens=int(response.get("eval_count", 0) or 0),
            time=(datetime.now() - start_datetime).total_seconds(),
        )

        kwargs: dict[str, Any] = {
            "content": content_blocks,
            "usage": usage,
            "metadata": metadata,
        }
        response_id = str(response.get("id", "") or "") if isinstance(response, dict) else ""
        if response_id:
            kwargs["id"] = response_id
        return ChatResponse(**kwargs)
