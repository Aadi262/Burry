#!/usr/bin/env python3
"""RAG knowledge base — inspired by AgentScope's SimpleKnowledge.
Index local files, docs, and notes. Search them semantically.
Burry can now answer 'what does the spec say about X' by reading your actual documents.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

KB_PATH = Path(__file__).parent / "knowledge_base"
KB_INDEX = KB_PATH / "index.json"
_AGENTSCOPE_KB = None


def _ensure_kb() -> None:
    KB_PATH.mkdir(exist_ok=True)
    if not KB_INDEX.exists():
        KB_INDEX.write_text(json.dumps({"documents": [], "chunks": []}))


def index_file(file_path: str, title: str = "") -> int:
    """Add a file to the knowledge base. Returns number of chunks indexed."""
    _ensure_kb()
    path = Path(file_path).expanduser()
    if not path.exists():
        return 0

    text = path.read_text(errors="ignore")
    # Split into overlapping chunks of ~500 words
    words = text.split()
    chunks = [" ".join(words[i:i+500]) for i in range(0, len(words), 400)]

    data = json.loads(KB_INDEX.read_text())

    doc_id = hashlib.md5(file_path.encode()).hexdigest()[:8]
    # Remove old version of this document if re-indexing
    data["documents"] = [d for d in data["documents"] if d.get("id") != doc_id]
    data["chunks"] = [c for c in data["chunks"] if c.get("doc_id") != doc_id]

    data["documents"].append({
        "id": doc_id,
        "path": str(path),
        "title": title or path.name,
        "chunks": len(chunks),
    })

    for i, chunk in enumerate(chunks):
        data["chunks"].append({
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}_{i}",
            "text": chunk,
            "title": title or path.name,
        })

    KB_INDEX.write_text(json.dumps(data, indent=2))
    return len(chunks)


def _search_custom_kb(query: str, top_k: int = 3) -> list[dict]:
    """Fallback keyword search over the local JSON knowledge base."""
    _ensure_kb()
    try:
        data = json.loads(KB_INDEX.read_text())
    except Exception:
        return []

    chunks = data.get("chunks", [])
    if not chunks:
        return []

    # Keyword scoring (fast, no embedding needed)
    query_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        chunk_words = set(chunk["text"].lower().split())
        score = len(query_words & chunk_words) / max(len(query_words), 1)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def _search_agentscope_kb(query: str, top_k: int = 3) -> list[dict]:
    """Best-effort adapter for an initialized AgentScope knowledge base."""
    kb = _AGENTSCOPE_KB
    if kb is None:
        return []

    for method_name, kwargs in (
        ("search", {"query": query, "top_k": top_k}),
        ("search", {"query": query, "k": top_k}),
        ("retrieve", {"query": query, "top_k": top_k}),
        ("retrieve", {"query": query, "k": top_k}),
    ):
        method = getattr(kb, method_name, None)
        if not callable(method):
            continue
        try:
            results = method(**kwargs)
        except TypeError:
            continue
        except Exception:
            return []
        break
    else:
        return []

    normalized: list[dict] = []
    for item in list(results or [])[:top_k]:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "Document").strip()
            text = str(item.get("text") or item.get("content") or "").strip()
        else:
            title = str(getattr(item, "title", "") or getattr(item, "name", "") or "Document").strip()
            text = str(getattr(item, "text", "") or getattr(item, "content", "") or item).strip()
        if text:
            normalized.append({"title": title or "Document", "text": text})
    return normalized


def search_knowledge_base(query: str, top_k: int = 3) -> list[dict]:
    """Search indexed documents. Uses AgentScope RAG if available, else custom KB."""
    try:
        from agentscope.rag import KnowledgeBase as _KnowledgeBase  # noqa: F401
    except ImportError:
        try:
            from agentscope.rag import KnowledgeBank as _KnowledgeBase  # type: ignore[attr-defined]  # noqa: F401
        except ImportError:
            _KnowledgeBase = None

    if _AGENTSCOPE_KB is not None:
        results = _search_agentscope_kb(query, top_k)
        if results:
            return results

    return _search_custom_kb(query, top_k)


def list_indexed_files() -> list[dict]:
    """Return list of all indexed documents."""
    _ensure_kb()
    try:
        data = json.loads(KB_INDEX.read_text())
        return data.get("documents", [])
    except Exception:
        return []
