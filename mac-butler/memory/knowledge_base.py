#!/usr/bin/env python3
"""RAG knowledge base — inspired by AgentScope's SimpleKnowledge.
Index local files, docs, and notes. Search them semantically.
Burry can now answer 'what does the spec say about X' by reading your actual documents.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import threading
from pathlib import Path

from butler_config import EMBED_MODEL, OLLAMA_LOCAL_URL

KB_PATH = Path(__file__).parent / "knowledge_base"
KB_INDEX = KB_PATH / "index.json"
_AGENTSCOPE_KB = None
_AGENTSCOPE_DOC_TITLES: dict[str, str] = {}
_KB_SUFFIXES = {".md", ".txt", ".py"}


def _ensure_kb() -> None:
    KB_PATH.mkdir(exist_ok=True)
    if not KB_INDEX.exists():
        KB_INDEX.write_text(json.dumps({"documents": [], "chunks": []}))


def _run_async(awaitable):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except BaseException as exc:
            error["exc"] = exc

    thread = threading.Thread(target=_runner, daemon=True, name="burry-rag-init")
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


def _iter_knowledge_files(data_dirs: list[str]):
    for data_dir in data_dirs:
        path = Path(data_dir).expanduser()
        if path.is_file() and path.suffix.lower() in _KB_SUFFIXES:
            yield path
            continue
        if not path.is_dir():
            continue
        for child in path.rglob("*"):
            if child.is_file() and child.suffix.lower() in _KB_SUFFIXES:
                yield child


def _detect_embedding_dimensions() -> int:
    try:
        from memory.store import _embed_text

        embedding = _embed_text("burry-rag-dimension-probe")
        if isinstance(embedding, list) and embedding:
            return len(embedding)
    except Exception:
        pass
    return 768


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
        ("retrieve", {"query": query, "limit": top_k}),
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
        if inspect.isawaitable(results):
            try:
                results = _run_async(results)
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
            metadata = getattr(item, "metadata", None)
            content = getattr(metadata, "content", None)
            if isinstance(content, dict):
                text = str(content.get("text") or content.get("content") or "").strip()
            else:
                text = str(getattr(item, "text", "") or getattr(item, "content", "") or item).strip()
            doc_id = str(getattr(metadata, "doc_id", "") or "").strip()
            title = _AGENTSCOPE_DOC_TITLES.get(
                doc_id,
                str(getattr(item, "title", "") or getattr(item, "name", "") or "Document").strip(),
            )
        if text:
            normalized.append({"title": title or "Document", "text": text})
    return normalized


def init_agentscope_rag(data_dirs: list[str]) -> bool:
    """Initialize AgentScope RAG for optional semantic search."""
    global _AGENTSCOPE_KB, _AGENTSCOPE_DOC_TITLES
    _AGENTSCOPE_KB = None
    _AGENTSCOPE_DOC_TITLES = {}
    try:
        from agentscope.rag import KnowledgeBank

        _AGENTSCOPE_KB = KnowledgeBank(
            configs=[
                {
                    "knowledge_id": "burry_docs",
                    "data_dirs_and_types": [(d, sorted(_KB_SUFFIXES)) for d in data_dirs],
                },
            ],
        )
        print(f"[RAG] AgentScope KnowledgeBank initialized with {len(data_dirs)} dirs")
        return True
    except ImportError:
        pass
    except Exception as exc:
        print(f"[RAG] AgentScope RAG not available: {exc} - using custom KB")
        return False

    try:
        from agentscope.embedding import OllamaTextEmbedding
        from agentscope.rag import MilvusLiteStore, SimpleKnowledge, TextReader

        _ensure_kb()
        files = list(_iter_knowledge_files(data_dirs))
        dimensions = _detect_embedding_dimensions()
        embedding_model = OllamaTextEmbedding(
            model_name=EMBED_MODEL,
            dimensions=dimensions,
            host=str(OLLAMA_LOCAL_URL or "http://127.0.0.1:11434").replace("localhost", "127.0.0.1"),
        )
        store = MilvusLiteStore(
            uri=str(KB_PATH / "agentscope_rag.db"),
            collection_name="burry_docs",
            dimensions=dimensions,
        )
        knowledge = SimpleKnowledge(
            embedding_store=store,
            embedding_model=embedding_model,
        )
        reader = TextReader(chunk_size=512, split_by="paragraph")

        async def _populate() -> None:
            documents = []
            for file_path in files:
                docs = await reader(str(file_path))
                for doc in docs:
                    metadata = getattr(doc, "metadata", None)
                    doc_id = str(getattr(metadata, "doc_id", "") or "").strip()
                    if doc_id:
                        _AGENTSCOPE_DOC_TITLES[doc_id] = file_path.name
                documents.extend(docs)
            if documents:
                await knowledge.add_documents(documents)

        _run_async(_populate())
        _AGENTSCOPE_KB = knowledge
        print(f"[RAG] AgentScope SimpleKnowledge initialized with {len(files)} files")
        return True
    except (ImportError, Exception) as exc:
        print(f"[RAG] AgentScope RAG not available: {exc} - using custom KB")
        return False


def search_knowledge_base(query: str, top_k: int = 3) -> list[dict]:
    """Search indexed documents. Uses AgentScope RAG if available, else custom KB."""
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
