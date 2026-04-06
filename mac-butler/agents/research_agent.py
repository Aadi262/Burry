#!/usr/bin/env python3
"""Deep Research Agent — multi-step parallel research with synthesis.
Inspired by AgentScope's research agent.

1. Decomposes question into 3 search queries
2. Runs all searches in parallel via ThreadPoolExecutor
3. Synthesizes into coherent answer
"""
from __future__ import annotations

import concurrent.futures

from brain.ollama_client import _call
from browser.agent import BrowsingAgent


def deep_research(question: str, model: str = "gemma4:e4b") -> str:
    """Multi-step research agent.

    Example: 'What are the latest trends in AI agents?'
    → 3 targeted searches → synthesis → one clear answer
    """
    # Step 1: Decompose into sub-queries
    decompose_prompt = f"""Break this research question into exactly 3 specific web search queries.
Return ONLY the 3 queries, one per line, no numbering or explanation.

Question: {question}

Queries:"""

    raw_queries = _call(decompose_prompt, model, max_tokens=100, temperature=0.1)
    queries = [q.strip() for q in (raw_queries or "").strip().split("\n") if q.strip()][:3]

    if not queries:
        queries = [question]

    # Step 2: Search all queries in parallel
    browser = BrowsingAgent()

    def search_one(q: str) -> str:
        try:
            result = browser.search(q, question=question)
            return result.get("result", "")
        except Exception:
            return ""

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(search_one, q) for q in queries]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    # Step 3: Synthesize
    combined = "\n\n---\n\n".join(r for r in results if r)
    if not combined:
        return "I couldn't find enough information on that topic."

    synthesis_prompt = f"""Research question: {question}

Research findings:
{combined[:4000]}

Provide a clear, concise answer in 3-5 sentences covering the key points:"""

    answer = _call(synthesis_prompt, model, max_tokens=300, temperature=0.2)
    return answer or combined[:500]
