#!/usr/bin/env python3
"""Benchmark configured Burry model roles on representative prompts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.runner import _is_low_signal_model_output, run_agent
from brain.ollama_client import _call, _provider_ready, pick_agent_model, pick_butler_model
from butler_config import AGENT_MODEL_CHAINS, BUTLER_MODEL_CHAINS, split_model_ref

BENCHMARK_CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "voice_brief",
        "family": "butler",
        "role": "voice",
        "prompt": "Rewrite this as one crisp spoken line under 22 words: Weather is clear, GitHub has two open issues, and the next task is reduce latency.",
        "max_tokens": 60,
        "temperature": 0.1,
        "timeout_hint": "voice",
    },
    {
        "name": "planning_next_step",
        "family": "butler",
        "role": "planning",
        "prompt": "Return only JSON with focus, why_now, question, and actions for this context: mac-butler has Phase 3B active, GitHub status just landed, and retrieval latency is still high.",
        "max_tokens": 120,
        "temperature": 0.0,
        "timeout_hint": "default",
    },
    {
        "name": "review_bug_summary",
        "family": "butler",
        "role": "review",
        "prompt": "Summarize the likely regression from this signal in under 45 words: planner routed weather correctly, but GitHub status fell back to generic search for 'any issues on adpilot'.",
        "max_tokens": 90,
        "temperature": 0.1,
        "timeout_hint": "agent",
    },
    {
        "name": "coding_patch_plan",
        "family": "butler",
        "role": "coding",
        "prompt": "List the next 3 code-level changes to reduce retrieval latency in a GitHub-status plus page-summary stack. Keep it under 70 words.",
        "max_tokens": 110,
        "temperature": 0.1,
        "timeout_hint": "agent",
    },
    {
        "name": "search_fact_agent",
        "family": "agent",
        "role": "search",
        "prompt": "Answer in one sentence: what is Qwen2.5?",
        "max_tokens": 80,
        "temperature": 0.0,
        "timeout_hint": "agent",
    },
    {
        "name": "github_status_agent",
        "family": "agent",
        "role": "github",
        "prompt": "Answer in one sentence: Aadi262/Adpilot has 2 open issues, 1 open pull request, and the latest push was today. What should the operator know first?",
        "max_tokens": 80,
        "temperature": 0.0,
        "timeout_hint": "agent",
    },
    {
        "name": "bugfinder_agent",
        "family": "agent",
        "role": "bugfinder",
        "prompt": "Summarize this failure in under 45 words: system_check phase3a browser passed, but reminder verification failed because Reminders automation access was missing.",
        "max_tokens": 80,
        "temperature": 0.0,
        "timeout_hint": "agent",
    },
)

RETRIEVAL_BENCHMARK_CASES: tuple[dict[str, Any], ...] = (
    {
        "name": "quick_fact_pm_india",
        "agent_type": "search",
        "input": {"query": "who is PM of India"},
        "expected_tool": "quick_fact",
        "latency_budget_s": 4.0,
    },
    {
        "name": "weather_new_delhi",
        "agent_type": "weather",
        "input": {"query": "weather in New Delhi"},
        "expected_tool": "weather_lookup",
        "latency_budget_s": 5.0,
    },
    {
        "name": "github_status_burry",
        "agent_type": "github",
        "input": {"query": "status of Aadi262/Burry"},
        "expected_tool": "repo_status",
        "latency_budget_s": 8.0,
    },
    {
        "name": "project_status_adpilot",
        "agent_type": "project_status",
        "input": {"query": "how is adpilot doing"},
        "expected_tool": "project_status",
        "latency_budget_s": 8.0,
    },
    {
        "name": "page_read_example",
        "agent_type": "fetch",
        "input": {"query": "read this https://example.com", "url": "https://example.com"},
        "expected_tool": "jina_fetch",
        "latency_budget_s": 8.0,
    },
    {
        "name": "news_ai_headlines",
        "agent_type": "news",
        "input": {"topic": "AI", "hours": 24},
        "expected_tool": "",
        "latency_budget_s": 10.0,
    },
)


def _matching_cases(case_names: list[str] | None = None) -> list[dict[str, Any]]:
    if not case_names:
        return [dict(case) for case in BENCHMARK_CASES]
    wanted = {str(name or "").strip().lower() for name in case_names if str(name or "").strip()}
    return [dict(case) for case in BENCHMARK_CASES if case["name"].lower() in wanted]


def _matching_retrieval_cases(case_names: list[str] | None = None) -> list[dict[str, Any]]:
    if not case_names:
        return [dict(case) for case in RETRIEVAL_BENCHMARK_CASES]
    wanted = {str(name or "").strip().lower() for name in case_names if str(name or "").strip()}
    return [dict(case) for case in RETRIEVAL_BENCHMARK_CASES if case["name"].lower() in wanted]


def _resolved_chain(case: dict[str, Any]) -> list[str]:
    family = str(case.get("family", "")).strip()
    role = str(case.get("role", "")).strip()
    if family == "butler":
        return list(BUTLER_MODEL_CHAINS.get(role, []))
    if family == "agent":
        return list(AGENT_MODEL_CHAINS.get(role, []))
    return []


def _pick_case_model(case: dict[str, Any]) -> str:
    family = str(case.get("family", "")).strip()
    role = str(case.get("role", "")).strip()
    if family == "butler":
        return pick_butler_model(role)
    if family == "agent":
        return pick_agent_model(role)
    raise ValueError(f"Unsupported benchmark family: {family}")


def _run_case(case: dict[str, Any], *, iterations: int = 1, execute: bool = True) -> dict[str, Any]:
    model = _pick_case_model(case)
    provider, model_name = split_model_ref(model)
    result: dict[str, Any] = {
        "name": case["name"],
        "family": case["family"],
        "role": case["role"],
        "selected_model": model,
        "selected_provider": provider,
        "selected_model_name": model_name,
        "chain": _resolved_chain(case),
        "iterations": max(1, int(iterations or 1)),
        "executed": bool(execute),
        "status": "planned",
        "latencies_s": [],
        "avg_latency_s": None,
        "response_excerpt": "",
        "error": "",
    }
    if not execute:
        return result

    latencies: list[float] = []
    response_excerpt = ""
    for _ in range(result["iterations"]):
        started = time.perf_counter()
        try:
            reply = _call(
                str(case.get("prompt", "")),
                model,
                temperature=float(case.get("temperature", 0.0) or 0.0),
                max_tokens=int(case.get("max_tokens", 80) or 80),
                timeout_hint=str(case.get("timeout_hint", "default") or "default"),
            )
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
            return result
        latencies.append(round(time.perf_counter() - started, 4))
        if not response_excerpt:
            response_excerpt = " ".join(str(reply or "").split())[:180]

    result["status"] = "ok"
    result["latencies_s"] = latencies
    result["avg_latency_s"] = round(sum(latencies) / len(latencies), 4) if latencies else None
    result["response_excerpt"] = response_excerpt
    return result


def _retrieval_result_error(payload: dict[str, Any], expected_tool: str = "") -> str:
    status = str(payload.get("status", "") or "").strip().lower()
    if status == "error":
        return str(payload.get("result", "") or payload.get("error", "") or "agent returned error")
    result_text = " ".join(str(payload.get("result", "") or "").split()).strip()
    if not result_text:
        return "agent returned empty result"
    if _is_low_signal_model_output(result_text):
        return "agent returned low-signal progress filler"
    normalized = result_text.lower()
    if normalized.startswith(("i couldn't ", "i could not ", "couldn't ", "could not ")):
        return "agent returned unavailable fallback"
    data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
    actual_tool = str(data.get("tool", "") or "").strip()
    if expected_tool and actual_tool != expected_tool:
        return f"expected tool {expected_tool}, got {actual_tool}"
    return ""


def _run_retrieval_case(case: dict[str, Any], *, iterations: int = 1, execute: bool = True) -> dict[str, Any]:
    agent_type = str(case.get("agent_type", "") or "").strip()
    model = pick_agent_model(agent_type)
    provider, model_name = split_model_ref(model)
    result: dict[str, Any] = {
        "name": case["name"],
        "agent_type": agent_type,
        "selected_model": model,
        "selected_provider": provider,
        "selected_model_name": model_name,
        "chain": list(AGENT_MODEL_CHAINS.get(agent_type, [])),
        "iterations": max(1, int(iterations or 1)),
        "executed": bool(execute),
        "status": "planned",
        "latencies_s": [],
        "avg_latency_s": None,
        "latency_budget_s": float(case.get("latency_budget_s", 0.0) or 0.0),
        "within_budget": None,
        "expected_tool": str(case.get("expected_tool", "") or "").strip(),
        "actual_tool": "",
        "result_excerpt": "",
        "error": "",
    }
    if not execute:
        return result

    latencies: list[float] = []
    result_excerpt = ""
    actual_tool = ""
    for _ in range(result["iterations"]):
        started = time.perf_counter()
        payload = run_agent(agent_type, dict(case.get("input", {}) or {}), model_override=model)
        latencies.append(round(time.perf_counter() - started, 4))
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else {}
        actual_tool = str(data.get("tool", "") or actual_tool or "").strip()
        error = _retrieval_result_error(payload, expected_tool=result["expected_tool"])
        if error:
            result["status"] = "error"
            result["error"] = error
            break
        if not result_excerpt:
            result_excerpt = " ".join(str(payload.get("result", "") or "").split())[:180]
    else:
        result["status"] = "ok"

    result["latencies_s"] = latencies
    result["avg_latency_s"] = round(sum(latencies) / len(latencies), 4) if latencies else None
    result["within_budget"] = (
        result["avg_latency_s"] <= result["latency_budget_s"]
        if result["avg_latency_s"] is not None and result["latency_budget_s"]
        else None
    )
    result["actual_tool"] = actual_tool
    result["result_excerpt"] = result_excerpt
    return result


def run_benchmarks(*, case_names: list[str] | None = None, iterations: int = 1, execute: bool = True) -> dict[str, Any]:
    cases = _matching_cases(case_names)
    results = [_run_case(case, iterations=iterations, execute=execute) for case in cases]
    ok = [item for item in results if item.get("status") == "ok"]
    errors = [item for item in results if item.get("status") == "error"]
    avg_latency = None
    if ok:
        latencies = [float(item.get("avg_latency_s") or 0.0) for item in ok if item.get("avg_latency_s") is not None]
        avg_latency = round(sum(latencies) / len(latencies), 4) if latencies else None
    return {
        "nvidia_ready": _provider_ready("nvidia"),
        "case_count": len(results),
        "executed": bool(execute),
        "results": results,
        "summary": {
            "ok": len(ok),
            "error": len(errors),
            "avg_latency_s": avg_latency,
        },
    }


def run_retrieval_benchmarks(
    *,
    case_names: list[str] | None = None,
    iterations: int = 1,
    execute: bool = True,
) -> dict[str, Any]:
    cases = _matching_retrieval_cases(case_names)
    results = [_run_retrieval_case(case, iterations=iterations, execute=execute) for case in cases]
    ok = [item for item in results if item.get("status") == "ok"]
    errors = [item for item in results if item.get("status") == "error"]
    over_budget = [
        item
        for item in ok
        if item.get("within_budget") is False
    ]
    latencies = [float(item.get("avg_latency_s") or 0.0) for item in ok if item.get("avg_latency_s") is not None]
    avg_latency = round(sum(latencies) / len(latencies), 4) if latencies else None
    return {
        "nvidia_ready": _provider_ready("nvidia"),
        "case_count": len(results),
        "executed": bool(execute),
        "results": results,
        "summary": {
            "ok": len(ok),
            "error": len(errors),
            "over_budget": len(over_budget),
            "avg_latency_s": avg_latency,
        },
    }


def run_full_benchmark_report(
    *,
    case_names: list[str] | None = None,
    task_case_names: list[str] | None = None,
    iterations: int = 1,
    execute: bool = True,
    include_retrieval: bool = False,
) -> dict[str, Any]:
    model_report = run_benchmarks(case_names=case_names, iterations=iterations, execute=execute)
    if not include_retrieval:
        return model_report
    retrieval_report = run_retrieval_benchmarks(
        case_names=task_case_names,
        iterations=iterations,
        execute=execute,
    )
    return {
        "nvidia_ready": model_report.get("nvidia_ready") or retrieval_report.get("nvidia_ready"),
        "executed": bool(execute),
        "model_benchmarks": model_report,
        "retrieval_benchmarks": retrieval_report,
        "summary": {
            "model_ok": model_report.get("summary", {}).get("ok", 0),
            "model_error": model_report.get("summary", {}).get("error", 0),
            "retrieval_ok": retrieval_report.get("summary", {}).get("ok", 0),
            "retrieval_error": retrieval_report.get("summary", {}).get("error", 0),
            "retrieval_over_budget": retrieval_report.get("summary", {}).get("over_budget", 0),
        },
    }


def _summary_lines(report: dict[str, Any]) -> list[str]:
    if "model_benchmarks" in report:
        lines = ["Model benchmarks:"]
        lines.extend(_summary_lines(report["model_benchmarks"]))
        lines.append("Retrieval task benchmarks:")
        lines.extend(_summary_lines(report["retrieval_benchmarks"]))
        return lines

    lines = [
        f"NVIDIA ready: {report.get('nvidia_ready')}",
        f"Cases: {report.get('case_count')} | Executed: {report.get('executed')}",
    ]
    for item in report.get("results", []):
        line = f"- {item['name']}: {item['selected_model']}"
        if item.get("status") == "ok":
            line += f" | avg {item.get('avg_latency_s')}s"
        elif item.get("status") == "error":
            line += f" | error {item.get('error')}"
        else:
            line += " | planned"
        lines.append(line)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Burry model routing on representative prompts")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--dry-run", action="store_true", help="Resolve routed models without executing prompts")
    parser.add_argument("--real-tasks", action="store_true", help="Also run end-to-end retrieval task benchmarks")
    parser.add_argument("--iterations", type=int, default=1, help="Runs per benchmark case")
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Benchmark only the named case; repeat to include more than one",
    )
    parser.add_argument(
        "--task-case",
        action="append",
        dest="task_cases",
        help="With --real-tasks, benchmark only the named retrieval task case; repeat to include more than one",
    )
    args = parser.parse_args()

    report = run_full_benchmark_report(
        case_names=args.cases,
        task_case_names=args.task_cases,
        iterations=max(1, int(args.iterations or 1)),
        execute=not args.dry_run,
        include_retrieval=args.real_tasks,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n".join(_summary_lines(report)))
    summary = report.get("summary", {})
    errors = int(summary.get("error", 0) or summary.get("model_error", 0) or 0)
    errors += int(summary.get("retrieval_error", 0) or 0)
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
