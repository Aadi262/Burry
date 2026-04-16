#!/usr/bin/env python3
"""Hermes-style structured output extraction using Pydantic.
Instead of fragile regex, use LLM to extract structured data from voice commands.
Inspired by NousResearch Hermes tool-calling approach.
"""
from __future__ import annotations

import json
import re
from typing import Optional, TypeVar

from pydantic import BaseModel

from butler_config import STRUCTURED_EXTRACTION_MODEL

T = TypeVar("T", bound=BaseModel)


class EmailIntent(BaseModel):
    recipient: str
    subject: Optional[str] = ""
    body: Optional[str] = ""


class ReminderIntent(BaseModel):
    minutes: int
    message: str


class SearchIntent(BaseModel):
    query: str
    time_sensitive: bool = False


def extract_structured(text: str, schema: type[T], model: str = STRUCTURED_EXTRACTION_MODEL) -> T | None:
    """Use LLM to extract structured data from natural language.
    Falls back to None if extraction fails.
    """
    from brain.ollama_client import _call

    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    prompt = f"""Extract information from this text and return ONLY valid JSON matching the schema.
No explanation. No markdown. Just the JSON object.

Schema:
{schema_json}

Text: "{text}"

JSON:"""

    raw = _call(prompt, model, max_tokens=150, temperature=0.0)

    # Strip markdown if present
    raw = re.sub(r"```json?\s*|\s*```", "", raw or "").strip()

    try:
        data = json.loads(raw)
        return schema(**data)
    except Exception:
        return None
