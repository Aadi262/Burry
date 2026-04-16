#!/usr/bin/env python3
"""Knowledge base backed by AgentScope SimpleKnowledge + QdrantStore.

Falls back to the local JSON keyword index whenever AgentScope RAG or the
embedding runtime is unavailable.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse

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


def _ollama_host() -> str:
  return str(OLLAMA_LOCAL_URL or "http://127.0.0.1:11434").replace("localhost", "127.0.0.1")


def _detect_embedding_dimensions() -> int:
  # nomic-embed-text always produces 768-dimensional vectors.
  # Previous implementation made a real embedding API call just to measure this,
  # adding ~1-2s latency to every RAG initialization.
  return 768


def _reader_documents(reader, text: str):
  documents = reader(text)
  if inspect.isawaitable(documents):
    documents = _run_async(documents)
  return list(documents or [])


def _record_agentscope_titles(documents: list, title: str) -> None:
  for document in documents:
    metadata = getattr(document, "metadata", None)
    doc_id = str(getattr(metadata, "doc_id", "") or "").strip()
    if doc_id:
      _AGENTSCOPE_DOC_TITLES[doc_id] = title


def _add_to_agentscope_kb(text: str, title: str) -> None:
  if _AGENTSCOPE_KB is None:
    return
  try:
    from agentscope.rag import TextReader

    reader = TextReader(chunk_size=512, split_by="paragraph")
    documents = _reader_documents(reader, text)
    if not documents:
      return
    _record_agentscope_titles(documents, title)
    _AGENTSCOPE_KB.add_documents(documents)
  except Exception:
    pass


def _load_index_data() -> dict:
  _ensure_kb()
  try:
    data = json.loads(KB_INDEX.read_text())
  except Exception:
    data = {"documents": [], "chunks": []}
  if not isinstance(data, dict):
    return {"documents": [], "chunks": []}
  data.setdefault("documents", [])
  data.setdefault("chunks", [])
  return data


def _write_index_data(data: dict) -> None:
  KB_INDEX.write_text(json.dumps(data, indent=2))


def _document_id(source: str) -> str:
  return hashlib.md5(str(source or "").encode()).hexdigest()[:8]


def _chunk_text(text: str, *, chunk_words: int = 500, overlap_words: int = 100) -> list[str]:
  words = str(text or "").split()
  if not words:
    return []
  step = max(chunk_words - overlap_words, 1)
  return [
    " ".join(words[index:index + chunk_words])
    for index in range(0, len(words), step)
  ]


def _default_title(source: str, title: str = "") -> str:
  cleaned = str(title or "").strip()
  if cleaned:
    return cleaned
  source_text = str(source or "").strip()
  if not source_text:
    return "document"
  parsed = urllib.parse.urlparse(source_text)
  if parsed.scheme and parsed.netloc:
    tail = Path(parsed.path).name.strip()
    return tail or parsed.netloc
  return Path(source_text).name or source_text


def _upsert_document(
  source: str,
  text: str,
  *,
  title: str = "",
  kind: str = "file",
  path: str = "",
  url: str = "",
) -> int:
  normalized_source = str(source or "").strip()
  body = str(text or "").strip()
  if not normalized_source or not body:
    return 0

  chunks = _chunk_text(body)
  if not chunks:
    return 0

  data = _load_index_data()
  doc_id = _document_id(normalized_source)
  updated_at = datetime.now(timezone.utc).isoformat()
  doc_title = _default_title(normalized_source, title)

  data["documents"] = [doc for doc in data["documents"] if doc.get("id") != doc_id]
  data["chunks"] = [chunk for chunk in data["chunks"] if chunk.get("doc_id") != doc_id]

  data["documents"].append({
    "id": doc_id,
    "source": normalized_source,
    "path": path,
    "url": url,
    "kind": kind,
    "title": doc_title,
    "chunks": len(chunks),
    "updated_at": updated_at,
  })

  for index, chunk in enumerate(chunks):
    data["chunks"].append({
      "doc_id": doc_id,
      "chunk_id": f"{doc_id}_{index}",
      "text": chunk,
      "title": doc_title,
      "source": normalized_source,
      "path": path,
      "url": url,
      "kind": kind,
      "updated_at": updated_at,
    })

  _write_index_data(data)
  return len(chunks)


def _index_custom_file(file_path: str, title: str = "") -> int:
  _ensure_kb()
  path = Path(file_path).expanduser()
  if not path.exists():
    return 0

  text = path.read_text(errors="ignore")
  return _upsert_document(
    str(path),
    text,
    title=title or path.name,
    kind="file",
    path=str(path),
  )


def init_agentscope_rag(data_dirs: list[str]) -> bool:
  """Initialize AgentScope SimpleKnowledge with a local Qdrant store."""
  global _AGENTSCOPE_KB, _AGENTSCOPE_DOC_TITLES
  _AGENTSCOPE_KB = None
  _AGENTSCOPE_DOC_TITLES = {}

  try:
    from agentscope.embedding import OllamaTextEmbedding
    from agentscope.rag import QdrantStore, SimpleKnowledge, TextReader

    _ensure_kb()
    dimensions = _detect_embedding_dimensions()
    embedding_model = OllamaTextEmbedding(
      model_name=EMBED_MODEL,
      dimensions=dimensions,
      host=_ollama_host(),
    )
    store = QdrantStore(
      location=str(KB_PATH / "qdrant"),
      collection_name="burry_docs",
      dimensions=dimensions,
    )
    knowledge = SimpleKnowledge(
      embedding_store=store,
      embedding_model=embedding_model,
    )

    reader = TextReader(chunk_size=512, split_by="paragraph")
    for file_path in _iter_knowledge_files(data_dirs):
      try:
        text = file_path.read_text(errors="ignore")
      except Exception:
        continue
      if not text.strip():
        continue
      documents = _reader_documents(reader, text)
      if not documents:
        continue
      _record_agentscope_titles(documents, file_path.name)
      knowledge.add_documents(documents)

    _AGENTSCOPE_KB = knowledge
    print("[RAG] AgentScope SimpleKnowledge initialized")
    return True
  except (ImportError, Exception) as exc:
    print(f"[RAG] AgentScope RAG not available: {exc}")
    return False


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

  query_words = set(str(query or "").lower().split())
  scored = []
  for chunk in chunks:
    chunk_words = set(str(chunk.get("text", "")).lower().split())
    score = len(query_words & chunk_words) / max(len(query_words), 1)
    if score > 0:
      scored.append((score, chunk))

  scored.sort(key=lambda item: item[0], reverse=True)
  return [chunk for _, chunk in scored[:top_k]]


def search_knowledge_base(query: str, top_k: int = 3) -> list[dict]:
  """Search using AgentScope RAG if available, custom KB otherwise."""
  if _AGENTSCOPE_KB is not None:
    try:
      results = _AGENTSCOPE_KB.retrieve(query, limit=top_k)
      normalized = []
      for result in list(results or [])[:top_k]:
        metadata = getattr(result, "metadata", None)
        content = getattr(metadata, "content", None)
        if isinstance(content, dict):
          text = str(content.get("text") or content.get("content") or "").strip()
        else:
          text = str(getattr(result, "text", "") or result).strip()
        doc_id = str(getattr(metadata, "doc_id", "") or "").strip()
        title = _AGENTSCOPE_DOC_TITLES.get(doc_id) or "doc"
        if text:
          normalized.append({"title": title, "text": text[:500]})
      if normalized:
        return normalized
    except Exception:
      pass
  return _search_custom_kb(query, top_k)


def index_file(file_path: str, title: str = "") -> int:
  """Add a file to the knowledge base."""
  count = _index_custom_file(file_path, title)
  path = Path(file_path).expanduser()
  if not path.exists():
    return count
  try:
    text = path.read_text(errors="ignore")
  except Exception:
    return count
  _add_to_agentscope_kb(text, title or path.name)
  return count


def index_web_page(url: str, text: str, title: str = "") -> int:
  """Cache fetched page text so repeated retrieval can reuse a local snapshot."""
  cleaned_url = str(url or "").strip()
  body = str(text or "").strip()
  if not cleaned_url or not body:
    return 0
  count = _upsert_document(
    cleaned_url,
    body,
    title=title,
    kind="web_page",
    url=cleaned_url,
  )
  _add_to_agentscope_kb(body, title or _default_title(cleaned_url))
  return count


def get_indexed_document(source: str) -> dict | None:
  """Return a cached document or page snapshot by exact source/path/URL."""
  cleaned_source = str(source or "").strip()
  if not cleaned_source:
    return None

  data = _load_index_data()
  documents = list(data.get("documents", []))
  chunks = list(data.get("chunks", []))

  for document in reversed(documents):
    fields = (
      str(document.get("source", "")).strip(),
      str(document.get("path", "")).strip(),
      str(document.get("url", "")).strip(),
    )
    if cleaned_source not in fields:
      continue
    doc_id = str(document.get("id", "")).strip()
    text = "\n\n".join(
      str(chunk.get("text", "")).strip()
      for chunk in chunks
      if str(chunk.get("doc_id", "")).strip() == doc_id and str(chunk.get("text", "")).strip()
    ).strip()
    if not text:
      return None
    return {**document, "text": text[:24000]}
  return None


def list_indexed_files() -> list[dict]:
  """Return the list of indexed documents from the fallback JSON store."""
  return list(_load_index_data().get("documents", []))
