#!/usr/bin/env python3
"""Agentic RL foundation — inspired by AgentScope's Trinity-RFT integration.
Tracks what works and what doesn't, improves model selection over time.
Not full RL training — a feedback loop that makes Burry smarter.

Pattern: outcome → score → adjust model selection → improve
"""
from __future__ import annotations

import json
import time
from pathlib import Path

RL_PATH = Path(__file__).parent / "rl_experience.json"


def _load() -> dict:
    try:
        return json.loads(RL_PATH.read_text())
    except Exception:
        return {"episodes": [], "intent_scores": {}, "model_scores": {}}


def _save(data: dict) -> None:
    RL_PATH.write_text(json.dumps(data, indent=2))


def record_episode(text: str, intent: str, model: str, response: str, outcome: str = "unknown") -> None:
    """Record a completed command episode.
    outcome: 'success', 'failure', 'partial', 'unknown'
    """
    data = _load()

    episode = {
        "text": text[:100],
        "intent": intent,
        "model": model,
        "response": response[:100],
        "outcome": outcome,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    data["episodes"].append(episode)
    data["episodes"] = data["episodes"][-500:]  # keep last 500

    # Update intent scores
    if intent not in data["intent_scores"]:
        data["intent_scores"][intent] = {"success": 0, "failure": 0, "total": 0}
    data["intent_scores"][intent]["total"] += 1
    if outcome == "success":
        data["intent_scores"][intent]["success"] += 1
    elif outcome == "failure":
        data["intent_scores"][intent]["failure"] += 1

    # Update model scores
    if model not in data["model_scores"]:
        data["model_scores"][model] = {"success": 0, "failure": 0, "total": 0}
    data["model_scores"][model]["total"] += 1
    if outcome == "success":
        data["model_scores"][model]["success"] += 1
    elif outcome == "failure":
        data["model_scores"][model]["failure"] += 1

    _save(data)


def record_episode_with_agentscope_feedback(
    text: str,
    intent: str,
    model: str,
    response: str,
    outcome: str,
) -> None:
    """Record an episode locally and reserve AgentScope tuner integration."""
    record_episode(text, intent, model, response, outcome)
    # TODO: Re-enable AgentScope tuner feedback once agentscope.tuner exposes
    # a stable record_feedback API in the installed package version.


def get_best_model_for_intent(intent: str, candidates: list[str]) -> str:
    """Return the model with best success rate for this intent type.
    Requires at least 5 episodes to trust the score.
    """
    if not candidates:
        return ""
    data = _load()
    model_scores = data.get("model_scores", {})

    best = candidates[0]
    best_rate = -1.0

    for model in candidates:
        scores = model_scores.get(model, {})
        total = scores.get("total", 0)
        if total >= 5:
            rate = scores.get("success", 0) / total
            if rate > best_rate:
                best_rate = rate
                best = model

    return best


def get_improvement_hints() -> str:
    """Generate improvement hints from episode history."""
    data = _load()
    intent_scores = data.get("intent_scores", {})

    hints = []
    for intent, scores in intent_scores.items():
        total = scores.get("total", 0)
        failures = scores.get("failure", 0)
        if total >= 3 and failures / total > 0.5:
            hints.append(
                f"- {intent} intent fails {int(failures/total*100)}% of the time — needs improvement"
            )

    return "\n".join(hints) if hints else "All intents performing well"


def get_stats() -> dict:
    """Return summary stats for dashboard/reporting."""
    data = _load()
    return {
        "total_episodes": len(data["episodes"]),
        "intent_count": len(data["intent_scores"]),
        "model_count": len(data["model_scores"]),
        "hints": get_improvement_hints(),
    }
